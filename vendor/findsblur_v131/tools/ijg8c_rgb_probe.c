/*
 * FindsBlur IJG 8c RGB probe — statically linked against official IJG jpeg-8c.
 * Arguments (Windows Unicode): input.jpg output_prefix islow|ifast|float fancy(0|1) smooth(0|1)
 * Creates <output_prefix>_RGB.raw, exactly width*height*3 interleaved RGB bytes.
 * No official EXE, source photos, or reference TXT are embedded.
 */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <wchar.h>
#include <string.h>
#include "jpeglib.h"

static int invalid(const char *message) {
    fprintf(stderr, "IJG8c RGB: %s\n", message);
    return 2;
}

int wmain(int argc, wchar_t **argv) {
    if (argc != 6) {
        return invalid("usage: ijg8c_rgb_probe.exe input.jpg prefix islow|ifast|float 0|1 0|1");
    }
    FILE *in = _wfopen(argv[1], L"rb");
    if (!in) return invalid("input JPEG could not be opened");
    struct jpeg_decompress_struct jpeg;
    struct jpeg_error_mgr err;
    jpeg.err = jpeg_std_error(&err);
    jpeg_create_decompress(&jpeg);
    jpeg_stdio_src(&jpeg, in);
    if (jpeg_read_header(&jpeg, TRUE) != JPEG_HEADER_OK) {
        jpeg_destroy_decompress(&jpeg);
        fclose(in);
        return invalid("JPEG header is invalid");
    }
    jpeg.out_color_space = JCS_RGB;
    if (wcscmp(argv[3], L"islow") == 0) jpeg.dct_method = JDCT_ISLOW;
    else if (wcscmp(argv[3], L"ifast") == 0) jpeg.dct_method = JDCT_IFAST;
    else if (wcscmp(argv[3], L"float") == 0) jpeg.dct_method = JDCT_FLOAT;
    else { jpeg_destroy_decompress(&jpeg); fclose(in); return invalid("unsupported DCT method"); }
    jpeg.do_fancy_upsampling = (wcscmp(argv[4], L"1") == 0) ? TRUE : FALSE;
    jpeg.do_block_smoothing = (wcscmp(argv[5], L"1") == 0) ? TRUE : FALSE;
    jpeg_start_decompress(&jpeg);
    const unsigned int width = jpeg.output_width;
    const unsigned int height = jpeg.output_height;
    if (jpeg.output_components != 3 || width == 0 || height == 0 ||
        (uint64_t)width * (uint64_t)height > UINT64_C(80000000)) {
        jpeg_destroy_decompress(&jpeg);
        fclose(in);
        return invalid("image size/components not supported");
    }
    const size_t row_bytes = (size_t)width * 3u;
    JSAMPARRAY scanline = (*jpeg.mem->alloc_sarray)((j_common_ptr)&jpeg, JPOOL_IMAGE, (JDIMENSION)row_bytes, 1);
    size_t cap = wcslen(argv[2]) + 32;
    wchar_t *outfile = (wchar_t *)calloc(cap, sizeof(wchar_t));
    if (!outfile) { jpeg_destroy_decompress(&jpeg); fclose(in); return invalid("out of memory"); }
    _snwprintf(outfile, cap - 1, L"%ls_RGB.raw", argv[2]);
    FILE *out = _wfopen(outfile, L"wb");
    free(outfile);
    if (!out) { jpeg_destroy_decompress(&jpeg); fclose(in); return invalid("output raw file could not be created"); }
    int ok = 1;
    while (jpeg.output_scanline < jpeg.output_height) {
        if (jpeg_read_scanlines(&jpeg, scanline, 1) != 1 ||
            fwrite(scanline[0], 1, row_bytes, out) != row_bytes) { ok = 0; break; }
    }
    if (fclose(out)) ok = 0;
    if (ok) jpeg_finish_decompress(&jpeg);
    jpeg_destroy_decompress(&jpeg);
    fclose(in);
    if (!ok) return invalid("could not write complete RGB buffer");
    printf("JPEG_LIB_VERSION=%d WIDTH=%u HEIGHT=%u DCT=%ls FANCY=%ls SMOOTH=%ls\n",
           JPEG_LIB_VERSION, width, height, argv[3], argv[4], argv[5]);
    fflush(stdout);
    return 0;
}
