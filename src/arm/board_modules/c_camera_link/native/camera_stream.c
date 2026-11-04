/* Keep the ATK RGB24 multiplanar V4L2 stream open; serve fresh P6 frames on demand. */
#include <errno.h>
#include <fcntl.h>
#include <linux/v4l2-subdev.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#if LM_CAMERA_JPEG
#include <time.h>
#include "preview_jpeg.h"

static uint64_t monotonic_us(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000000 + now.tv_nsec / 1000;
}
static void store32(unsigned char *out, uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) out[i] = (unsigned char)(value >> (i * 8));
}
#endif

static volatile sig_atomic_t stopped;
static void stop(int signal_number) { (void)signal_number; stopped = 1; }
static int control(int fd, unsigned long request, void *arg) {
    int result;
    do result = ioctl(fd, request, arg); while (result < 0 && errno == EINTR && !stopped);
    return result;
}
static int send_all(const void *data, size_t size) {
    const unsigned char *p = data;
    while (size && !stopped) {
        ssize_t n = write(STDOUT_FILENO, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n; size -= (size_t)n;
    }
    return size ? -1 : 0;
}
int main(int argc, char **argv) {
    int fd = -1, sub = -1, streaming = 0, result = 1;
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    void *maps[4] = {0}; size_t sizes[4] = {0}; unsigned count = 0;
    unsigned char *latest = NULL;
#if LM_CAMERA_JPEG
    unsigned jpeg_width = 320, jpeg_quality = 50;
    PreviewJpeg *jpeg = NULL;
    uint64_t requested_us = 0;
    if (argc != 3 || strspn(argv[1], "0123456789") != strlen(argv[1]) ||
        strspn(argv[2], "0123456789") != strlen(argv[2]) ||
        strlen(argv[1]) > 4 || strlen(argv[2]) > 2 ||
        (jpeg_width = (unsigned)strtoul(argv[1], NULL, 10)) < 16 || jpeg_width > 800 ||
        (jpeg_quality = (unsigned)strtoul(argv[2], NULL, 10)) < 10 || jpeg_quality > 95) {
        fprintf(stderr, "Usage: camera_jpeg_stream WIDTH(16..800) QUALITY(10..95)\n");
        return 2;
    }
    jpeg = calloc(1, sizeof(*jpeg));
    if (!jpeg) goto cleanup;
#else
    (void)argc; (void)argv;
#endif
    signal(SIGTERM, stop); signal(SIGINT, stop); signal(SIGPIPE, stop);
    sub = open("/dev/v4l-subdev0", O_RDWR);
    if (sub < 0) { perror("open subdev"); goto cleanup; }
    struct v4l2_subdev_format sensor = {0};
    sensor.which = V4L2_SUBDEV_FORMAT_ACTIVE;
    if (control(sub, VIDIOC_SUBDEV_G_FMT, &sensor) < 0) { perror("subdev G_FMT"); goto cleanup; }
    sensor.format.width = 800; sensor.format.height = 480; sensor.format.field = V4L2_FIELD_NONE;
    if (control(sub, VIDIOC_SUBDEV_S_FMT, &sensor) < 0 || sensor.format.width != 800 || sensor.format.height != 480) {
        fprintf(stderr, "Sensor rejected 800x480\n"); goto cleanup;
    }
    close(sub); sub = -1;
    fd = open("/dev/video0", O_RDWR | O_NONBLOCK);
    if (fd < 0) { perror("open video0"); goto cleanup; }
    struct v4l2_capability cap = {0};
    if (control(fd, VIDIOC_QUERYCAP, &cap) < 0) { perror("QUERYCAP"); goto cleanup; }
    unsigned caps = cap.capabilities & V4L2_CAP_DEVICE_CAPS ? cap.device_caps : cap.capabilities;
    if (!(caps & V4L2_CAP_VIDEO_CAPTURE_MPLANE) || !(caps & V4L2_CAP_STREAMING)) {
        fprintf(stderr, "Need multiplanar streaming capture\n"); goto cleanup;
    }
    struct v4l2_format fmt = {0}; fmt.type = type;
    fmt.fmt.pix_mp.width = 800; fmt.fmt.pix_mp.height = 480;
    fmt.fmt.pix_mp.pixelformat = V4L2_PIX_FMT_RGB24;
    fmt.fmt.pix_mp.field = V4L2_FIELD_NONE; fmt.fmt.pix_mp.num_planes = 1;
    fmt.fmt.pix_mp.plane_fmt[0].bytesperline = 2400;
    fmt.fmt.pix_mp.plane_fmt[0].sizeimage = 1152000;
    if (control(fd, VIDIOC_S_FMT, &fmt) < 0) { perror("S_FMT"); goto cleanup; }
    if (control(fd, VIDIOC_G_FMT, &fmt) < 0) { perror("G_FMT"); goto cleanup; }
    unsigned stride = fmt.fmt.pix_mp.plane_fmt[0].bytesperline;
    if (fmt.fmt.pix_mp.width != 800 || fmt.fmt.pix_mp.height != 480 ||
        fmt.fmt.pix_mp.pixelformat != V4L2_PIX_FMT_RGB24 || fmt.fmt.pix_mp.num_planes != 1 || stride < 2400) {
        fprintf(stderr, "Unexpected video format; no guessed conversion\n"); goto cleanup;
    }
    latest = malloc(1152000);
    if (!latest) goto cleanup;
    struct v4l2_requestbuffers req = {0}; req.count = 4; req.type = type; req.memory = V4L2_MEMORY_MMAP;
    if (control(fd, VIDIOC_REQBUFS, &req) < 0 || !req.count || req.count > 4) {
        fprintf(stderr, "REQBUFS failed\n"); goto cleanup;
    }
    count = req.count;
    for (unsigned i = 0; i < count; ++i) {
        struct v4l2_plane planes[VIDEO_MAX_PLANES] = {0};
        struct v4l2_buffer b = {0}; b.type = type; b.memory = V4L2_MEMORY_MMAP;
        b.index = i; b.length = VIDEO_MAX_PLANES; b.m.planes = planes;
        if (control(fd, VIDIOC_QUERYBUF, &b) < 0 || b.length != 1) { perror("QUERYBUF"); goto cleanup; }
        sizes[i] = planes[0].length;
        maps[i] = mmap(NULL, sizes[i], PROT_READ | PROT_WRITE, MAP_SHARED, fd, planes[0].m.mem_offset);
        if (maps[i] == MAP_FAILED) { maps[i] = NULL; perror("mmap"); goto cleanup; }
        if (control(fd, VIDIOC_QBUF, &b) < 0) { perror("QBUF"); goto cleanup; }
    }
    if (control(fd, VIDIOC_STREAMON, &type) < 0) { perror("STREAMON"); goto cleanup; }
    streaming = 1;
    fprintf(stderr, "STREAM_OPEN 800x480 RGB24 stride=%u; no autofocus/flash commands\n", stride);
#if LM_CAMERA_JPEG
    fprintf(stderr, "JPEG_STREAM fps-v2 width=%u quality=%u; direct JPEG pipe, reusable encoder\n",
            jpeg_width, jpeg_quality);
#endif
    unsigned warmup = 0; int pending = 0, available = 0;
    while (!stopped) {
        struct pollfd pollfds[2] = {{fd, POLLIN, 0}, {STDIN_FILENO, pending ? 0 : POLLIN, 0}};
        int n = poll(pollfds, 2, 5000);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { fprintf(stderr, "Capture poll failed/timed out\n"); goto cleanup; }
        if (pollfds[1].revents & (POLLHUP | POLLERR | POLLNVAL)) { result = 0; break; }
        if (pollfds[1].revents & POLLIN) {
            char command;
            if (read(STDIN_FILENO, &command, 1) != 1) { result = 0; break; }
#if LM_CAMERA_JPEG
            if (command != 'J') { fprintf(stderr, "Invalid JPEG request\n"); goto cleanup; }
            requested_us = monotonic_us();
#else
            if (command != 'F') { fprintf(stderr, "Invalid frame request\n"); goto cleanup; }
#endif
            pending = 1;
        }
        if (pollfds[0].revents & (POLLERR | POLLHUP | POLLNVAL)) { fprintf(stderr, "Video poll error\n"); goto cleanup; }
        if (pollfds[0].revents & POLLIN) {
            /* Drain only a bounded queue snapshot so a fast camera cannot starve requests. */
            for (unsigned i = 0; i < count; ++i) {
                struct v4l2_plane planes[VIDEO_MAX_PLANES] = {0};
                struct v4l2_buffer b = {0}; b.type = type; b.memory = V4L2_MEMORY_MMAP;
                b.length = VIDEO_MAX_PLANES; b.m.planes = planes;
                if (control(fd, VIDIOC_DQBUF, &b) < 0) {
                    if (errno == EAGAIN) break;
                    perror("DQBUF"); goto cleanup;
                }
                size_t offset = planes[0].data_offset;
                size_t needed = (size_t)stride * 479 + 2400;
                if (b.index >= count || b.length != 1 || offset > sizes[b.index] ||
                    needed > sizes[b.index] - offset || planes[0].bytesused < offset + needed ||
                    (b.flags & V4L2_BUF_FLAG_ERROR)) {
                    fprintf(stderr, "Invalid/short captured frame\n"); goto cleanup;
                }
                for (unsigned y = 0; y < 480; ++y)
                    memcpy(latest + y * 2400, (unsigned char *)maps[b.index] + offset + y * stride, 2400);
                if (control(fd, VIDIOC_QBUF, &b) < 0) { perror("requeue"); goto cleanup; }
                if (warmup < 10) ++warmup;
                available = warmup >= 10;
            }
            if (pending && available) {
#if LM_CAMERA_JPEG
                uint64_t captured_us = monotonic_us();
                if (!preview_encode(jpeg, latest, 800, 480, 2400, jpeg_width, jpeg_quality)) {
                    fprintf(stderr, "JPEG encoding failed\n"); goto cleanup;
                }
                uint64_t encoded_us = monotonic_us();
                unsigned char prefix[12];
                store32(prefix, (uint32_t)jpeg->used);
                store32(prefix + 4, (uint32_t)(captured_us - requested_us));
                store32(prefix + 8, (uint32_t)(encoded_us - captured_us));
                if (send_all(prefix, sizeof(prefix)) || send_all(jpeg->data, jpeg->used)) goto cleanup;
#else
                static const char header[] = "P6\n800 480\n255\n";
                uint32_t length = 1152000 + sizeof(header) - 1;
                unsigned char prefix[4] = {length & 255, (length >> 8) & 255, (length >> 16) & 255, length >> 24};
                if (send_all(prefix, 4) || send_all(header, sizeof(header)-1) || send_all(latest, 1152000)) goto cleanup;
#endif
                pending = 0; available = 0;
            }
        }
    }
    if (stopped) result = 0;
cleanup:
    if (streaming) { control(fd, VIDIOC_STREAMOFF, &type); fprintf(stderr, "STREAM_CLOSED\n"); }
    for (unsigned i = 0; i < count; ++i) if (maps[i]) munmap(maps[i], sizes[i]);
    free(latest);
#if LM_CAMERA_JPEG
    preview_free(jpeg);
#endif
    if (fd >= 0) close(fd);
    if (sub >= 0) close(sub);
    return result;
}
