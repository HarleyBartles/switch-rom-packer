// forwarder/source/main.c
#include <switch.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <sys/stat.h>   // mkdir

#define LOG_DIR   "sdmc:/switch-rom-packer"
#define LOG_PATH  LOG_DIR "/forwarder.log"
#define ARG_FILE  "romfs:/nextArgv"
#define NRO_FILE  "romfs:/nextNroPath"

// -------- logging helpers --------
static void ensure_log_dir(void) {
    mkdir(LOG_DIR, 0777);
}

static void log_msg(const char* s) {
    ensure_log_dir();
    FILE* f = fopen(LOG_PATH, "a");
    if (f) { fprintf(f, "%s\n", s); fclose(f); }
}

static void log_printf(const char* fmt, ...) {
    ensure_log_dir();
    FILE* f = fopen(LOG_PATH, "a");
    if (!f) return;
    va_list ap; va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    fprintf(f, "\n");
    va_end(ap);
    fclose(f);
}

static void read_text_file(const char* path, char* out, size_t outsz) {
    out[0] = 0;
    FILE* f = fopen(path, "rb");
    if (!f) return;
    size_t n = fread(out, 1, outsz - 1, f);
    fclose(f);
    // trim trailing whitespace/newlines
    while (n && (out[n-1] == '\n' || out[n-1] == '\r' || out[n-1] == ' ' || out[n-1] == '\t')) n--;
    out[n] = 0;
}

// Placeholder: we’ll wire the hbloader handoff here next.
static Result chainload_nro(const char* nroPath, const char* argvLine) {
    (void)nroPath; (void)argvLine;
    // Custom stub error (module 346, desc 1) just to show something non-zero
    return MAKERESULT(346, 1);
}

int main(int argc, char* argv[]) {
    (void)argc; (void)argv;

    // Init services & filesystems
    fsInitialize();         // FS service first
    fsdevMountSdmc();       // enables stdio on sdmc:/
    romfsInit();            // mount romfs:/

    log_msg("SRP forwarder start");

    // Read parameters from romfs
    char nroPath[512];
    char argvLine[768];
    read_text_file(NRO_FILE, nroPath, sizeof(nroPath));
    read_text_file(ARG_FILE, argvLine, sizeof(argvLine));

    log_printf("nextNroPath=%s", nroPath[0] ? nroPath : "(missing)");
    log_printf("nextArgv=%s",    argvLine[0] ? argvLine : "(missing)");

    // Simple on-screen feedback
    consoleInit(NULL);
    printf("Switch ROM Packer Forwarder\n\n");

    if (!nroPath[0]) {
        printf("Error: romfs:/nextNroPath missing\n");
        log_msg("ERROR: nextNroPath missing");
    } else {
        printf("Target NRO:\n%s\n\n", nroPath);
        Result rc = chainload_nro(nroPath, argvLine);
        if (R_FAILED(rc)) {
            printf("Launch not implemented yet (rc=0x%x)\n", rc);
            log_printf("chainload_nro not implemented (rc=0x%x)", rc);
        }
    }
    printf("\nPress + to exit.\n");

    // Modern input API (pad*)
    PadState pad;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);

    while (appletMainLoop()) {
        padUpdate(&pad);
        u64 kDown = padGetButtonsDown(&pad);
        if (kDown & HidNpadButton_Plus) break;
        consoleUpdate(NULL);
    }
    consoleExit(NULL);

    // Cleanup
    romfsExit();
    fsdevUnmountAll();
    fsExit();
    return 0;
}
