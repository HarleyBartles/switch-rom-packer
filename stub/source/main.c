#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#include <switch.h>

#define OUTPUT_BASE "/roms/"
#define FILELIST    "filelist.txt"   // lines: "<platform>\t<filename>"

static int mkpath(const char* path) {
    // mkdir -p
    char tmp[1024];
    size_t len = strnlen(path, sizeof(tmp) - 1);
    if (len == 0) return 0;
    memcpy(tmp, path, len);
    tmp[len] = '\0';

    for (char *p = tmp + 1; *p; ++p) {
        if (*p == '/') {
            *p = '\0';
            mkdir(tmp, 0777); // ignore EEXIST
            *p = '/';
        }
    }
    if (mkdir(tmp, 0777) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static Result copyFile(const char* srcPath, const char* dstPath) {
    FILE* src = fopen(srcPath, "rb");
    if (!src) return MAKERESULT(Module_Libnx, LibnxError_NotFound);

    // Ensure destination directory exists
    char dir[1024];
    strncpy(dir, dstPath, sizeof(dir));
    dir[sizeof(dir)-1] = '\0';
    char *lastSlash = strrchr(dir, '/');
    if (lastSlash) { *lastSlash = '\0'; mkpath(dir); }

    FILE* dst = fopen(dstPath, "wb");
    if (!dst) { fclose(src); return MAKERESULT(Module_Libnx, LibnxError_IoError); }

    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0) {
        if (fwrite(buf, 1, n, dst) != n) {
            fclose(src); fclose(dst);
            return MAKERESULT(Module_Libnx, LibnxError_IoError);
        }
    }
    fclose(src); fclose(dst);
    return 0;
}

int main(int argc, char* argv[])
{
    consoleInit(NULL);

    Result rc = romfsInit();
    if (R_FAILED(rc)) {
        printf("romfsInit failed: 0x%x\n", rc);
    } else {
        char listPath[128];
        snprintf(listPath, sizeof(listPath), "romfs:/%s", FILELIST);

        FILE* list = fopen(listPath, "r");
        if (!list) {
            printf("Missing %s in RomFS.\n", FILELIST);
        } else {
            char line[768];
            while (fgets(line, sizeof(line), list)) {
                // Trim CR/LF
                size_t len = strlen(line);
                while (len && (line[len-1] == '\n' || line[len-1] == '\r')) line[--len] = '\0';
                if (!len) continue;

                // Parse "<platform>\t<filename>"
                char platform[160] = {0};
                char filename[576] = {0};
                if (sscanf(line, "%159[^\t]\t%575[^\n]", platform, filename) != 2) {
                    printf("Bad manifest line: %s\n", line);
                    continue;
                }

                char srcPath[700];
                char dstPath[1100];

                snprintf(srcPath, sizeof(srcPath), "romfs:/%s", filename);
                snprintf(dstPath, sizeof(dstPath), OUTPUT_BASE "%s/%s", platform, filename);

                printf("Copying %s -> %s\n", srcPath, dstPath);
                rc = copyFile(srcPath, dstPath);
                if (R_FAILED(rc)) printf("  Copy failed: 0x%x\n", rc);
                else              printf("  Done.\n");
            }
            fclose(list);
        }
        romfsExit();
    }

    // PadState input loop (libnx 4.9.0+)
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
