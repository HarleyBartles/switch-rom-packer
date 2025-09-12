#include <stdio.h>
#include <switch.h>

#define OUTPUT_DIR "/switch/roms/"
#define ROM_NAME   "rom.bin"   // name of bundled ROM in stub/romfs/

Result copyFile(const char* srcPath, const char* dstPath) {
    FILE* src = fopen(srcPath, "rb");
    if (!src) return MAKERESULT(Module_Libnx, LibnxError_NotFound);

    FILE* dst = fopen(dstPath, "wb");
    if (!dst) {
        fclose(src);
        return MAKERESULT(Module_Libnx, LibnxError_IoError);
    }

    char buf[8192];
    size_t read;
    while ((read = fread(buf, 1, sizeof(buf), src)) > 0) {
        fwrite(buf, 1, read, dst);
    }

    fclose(src);
    fclose(dst);
    return 0;
}

int main(int argc, char* argv[])
{
    consoleInit(NULL);

    Result rc = romfsInit();
    if (R_FAILED(rc)) {
        printf("romfsInit failed: 0x%x\n", rc);
    } else {
        printf("RomFS mounted.\n");

        char srcPath[64];
        char dstPath[256];

        snprintf(srcPath, sizeof(srcPath), "romfs:/%s", ROM_NAME);
        snprintf(dstPath, sizeof(dstPath), OUTPUT_DIR "%s", ROM_NAME);

        printf("Copying %s -> %s\n", srcPath, dstPath);
        rc = copyFile(srcPath, dstPath);
        if (R_FAILED(rc)) {
            printf("Copy failed: 0x%x\n", rc);
        } else {
            printf("Copy complete.\n");
        }

        romfsExit();
    }

    // --- PadState input loop (libnx 4.9.0) ---
    PadState pad;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);

    printf("Press PLUS to exit.\n");
    while (appletMainLoop()) {
        padUpdate(&pad);
        u64 kDown = padGetButtonsDown(&pad);
        if (kDown & HidNpadButton_Plus) break;

        consoleUpdate(NULL);
    }

    consoleExit(NULL);
    return 0;
}
