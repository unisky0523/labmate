/* Bounded preview encoder shared by file conversion and persistent capture. */
#ifndef LABMATE_PREVIEW_JPEG_H
#define LABMATE_PREVIEW_JPEG_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#define STBI_WRITE_NO_STDIO
#include "third_party/stb_image_write.h"

#define PREVIEW_MAX_PIXELS (16u * 1024u * 1024u)
#define PREVIEW_MAX_JPEG 32768u
#define PREVIEW_MAX_WIDTH 8192u

typedef struct {
    unsigned char data[PREVIEW_MAX_JPEG];
    unsigned char *pixels;
    size_t capacity, used;
    unsigned width, height;
    int overflow;
    unsigned x_offset[PREVIEW_MAX_WIDTH];
} PreviewJpeg;

static void preview_write(void *context, void *data, int size) {
    PreviewJpeg *jpeg = context;
    if (size < 0 || jpeg->overflow || (size_t)size > PREVIEW_MAX_JPEG - jpeg->used) {
        jpeg->overflow = 1;
        return;
    }
    memcpy(jpeg->data + jpeg->used, data, (size_t)size);
    jpeg->used += (size_t)size;
}

static int preview_encode(PreviewJpeg *jpeg, const unsigned char *rgb,
                          unsigned width, unsigned height, size_t stride,
                          unsigned max_width, unsigned quality) {
    if (!width || !height || (uint64_t)width * height > PREVIEW_MAX_PIXELS ||
        stride < (size_t)width * 3 || max_width < 16 || max_width > PREVIEW_MAX_WIDTH ||
        quality < 10 || quality > 95) return 0;
    unsigned out_w = width > max_width ? max_width : width;
    unsigned out_h = (unsigned)((uint64_t)height * out_w / width);
    if (!out_h) out_h = 1;
    size_t needed = (size_t)out_w * out_h * 3;
    if (needed > jpeg->capacity) {
        unsigned char *pixels = realloc(jpeg->pixels, needed);
        if (!pixels) return 0;
        jpeg->pixels = pixels;
        jpeg->capacity = needed;
    }
    for (int attempt = 0; attempt < 12; ++attempt) {
        /* Hoist 64-bit division out of the pixel loop on Cortex-A9. */
        for (unsigned x = 0; x < out_w; ++x)
            jpeg->x_offset[x] = (unsigned)((uint64_t)x * width / out_w) * 3;
        for (unsigned y = 0; y < out_h; ++y) {
            const unsigned char *row = rgb + (size_t)((uint64_t)y * height / out_h) * stride;
            unsigned char *dest = jpeg->pixels + (size_t)y * out_w * 3;
            for (unsigned x = 0; x < out_w; ++x)
                memcpy(dest + x * 3, row + jpeg->x_offset[x], 3);
        }
        jpeg->used = 0;
        jpeg->overflow = 0;
        int ok = stbi_write_jpg_to_func(preview_write, jpeg, (int)out_w, (int)out_h,
                                       3, jpeg->pixels, (int)quality);
        if (ok && !jpeg->overflow && jpeg->used >= 4) {
            jpeg->width = out_w;
            jpeg->height = out_h;
            return 1;
        }
        if (out_w == 1 && out_h == 1) break;
        out_w = out_w > 1 ? (out_w * 4 / 5 ? out_w * 4 / 5 : 1) : 1;
        out_h = out_h > 1 ? (out_h * 4 / 5 ? out_h * 4 / 5 : 1) : 1;
    }
    return 0;
}

static void preview_free(PreviewJpeg *jpeg) {
    if (jpeg) { free(jpeg->pixels); free(jpeg); }
}
#endif
