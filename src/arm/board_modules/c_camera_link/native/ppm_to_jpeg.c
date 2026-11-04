/* P6 RGB capture -> bounded JPEG, with no camera or autofocus operations. */
#include <ctype.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "preview_jpeg.h"

#define MAX_PIXELS (16u * 1024u * 1024u)

static int token(FILE *f, char *out, size_t capacity) {
    int ch;
    do {
        ch = fgetc(f);
        if (ch == '#') while (ch != '\n' && ch != EOF) ch = fgetc(f);
    } while (ch != EOF && isspace((unsigned char)ch));
    size_t used = 0;
    while (ch != EOF && !isspace((unsigned char)ch)) {
        if (used + 1 >= capacity) return 0;
        out[used++] = (char)ch;
        ch = fgetc(f);
    }
    if (ch == '\r') {
        int next = fgetc(f);
        if (next != '\n' && next != EOF) ungetc(next, f);
    }
    out[used] = 0;
    return used > 0;
}

static int number(FILE *f, unsigned *value) {
    char text[32], *end;
    if (!token(f, text, sizeof(text)) || !isdigit((unsigned char)text[0])) return 0;
    errno = 0;
    unsigned long n = strtoul(text, &end, 10);
    if (errno || *end || !n || n > MAX_PIXELS) return 0;
    *value = (unsigned)n;
    return 1;
}

static int option_number(const char *text, unsigned low, unsigned high, unsigned *value) {
    char *end;
    errno = 0;
    if (!isdigit((unsigned char)text[0])) return 0;
    unsigned long n = strtoul(text, &end, 10);
    if (errno || *end || n < low || n > high) return 0;
    *value = (unsigned)n;
    return 1;
}

int main(int argc, char **argv) {
    unsigned max_width = 480, quality = 60;
    if ((argc != 3 && argc != 5) || !strcmp(argv[1], argv[2]) ||
        (argc == 5 && (!option_number(argv[3], 16, 8192, &max_width) ||
                       !option_number(argv[4], 10, 95, &quality)))) {
        fprintf(stderr, "Usage: ppm_to_jpeg INPUT.ppm OUTPUT.jpg [WIDTH(16..8192) QUALITY(10..95)]\n"); return 2;
    }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("open input"); return 1; }
    char magic[8];
    unsigned width, height, depth;
    if (!token(f, magic, sizeof(magic)) || strcmp(magic, "P6") ||
        !number(f, &width) || !number(f, &height) || !number(f, &depth) ||
        depth != 255 || (uint64_t)width * height > MAX_PIXELS) {
        fprintf(stderr, "Expected bounded P6 RGB PPM with maxval 255\n"); fclose(f); return 1;
    }
    size_t size = (size_t)width * height * 3;
    unsigned char *rgb = (unsigned char *)malloc(size);
    if (!rgb || fread(rgb, 1, size, f) != size) {
        fprintf(stderr, "Insufficient memory or truncated PPM\n"); free(rgb); fclose(f); return 1;
    }
    fclose(f);
    PreviewJpeg *jpeg = calloc(1, sizeof(*jpeg));
    if (!jpeg) { fprintf(stderr, "Insufficient memory\n"); free(rgb); return 1; }
    int result = 1;
    if (preview_encode(jpeg, rgb, width, height, (size_t)width * 3, max_width, quality)) {
        FILE *out = fopen(argv[2], "wb");
        if (!out) perror("open output");
        else {
            int written = fwrite(jpeg->data, 1, jpeg->used, out) == jpeg->used;
            int closed = fclose(out) == 0;
            if (!written || !closed) { fprintf(stderr, "JPEG write failed\n"); remove(argv[2]); }
            else {
                printf("JPEG_SAVED width=%u height=%u bytes=%lu\n", jpeg->width, jpeg->height, (unsigned long)jpeg->used);
                result = 0;
            }
        }
    }
    if (result) fprintf(stderr, "No JPEG produced\n");
    free(rgb); preview_free(jpeg);
    return result;
}
