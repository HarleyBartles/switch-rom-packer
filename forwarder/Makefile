# forwarder/Makefile
# Build a minimal libnx forwarder: exefs/main (NSO) + main.npdm

DEVKITPRO ?= /opt/devkitpro

# --- Project layout ---
TARGET    := forwarder
BUILD     := build
SRC_DIR   := source
INC_DIR   := include
OUTDIR    := out
EXEFSDIR  := $(OUTDIR)/exefs
ELF       := $(BUILD)/$(TARGET).elf
NSO       := $(EXEFSDIR)/main
NPDM_JSON := npdm.json
NPDM      := $(EXEFSDIR)/main.npdm

# Bring in toolchain, default flags, etc.
include $(DEVKITPRO)/libnx/switch_rules

# Tools from switch-tools (installed via dkp-pacman)
ELF2NSO   := elf2nso
NPDMTOOL  := npdmtool

# Source/object lists
SRCS := $(wildcard $(SRC_DIR)/*.c)
OBJS := $(patsubst $(SRC_DIR)/%.c,$(BUILD)/%.o,$(SRCS))

# ---- Includes ----
CPPFLAGS += -I$(DEVKITPRO)/libnx/include \
            -I$(DEVKITPRO)/portlibs/switch/include \
            -I$(INC_DIR)

# ---- Link against libnx ----
LIBDIRS  := $(DEVKITPRO)/libnx/lib $(DEVKITPRO)/portlibs/switch/lib
LDFLAGS += -specs=$(DEVKITPRO)/libnx/switch.specs \
           $(addprefix -L,$(LIBDIRS)) \
           -Wl,--gc-sections -fPIE
LIBS    += -lnx
CFLAGS  += -fPIE

# Optional: sane warnings/optimizations
CFLAGS  += -O2 -ffunction-sections -fdata-sections -Wall

.PHONY: all clean print-vars
all: $(NSO) $(NPDM)

# Compile each C file
$(BUILD)/%.o: $(SRC_DIR)/%.c
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(CPPFLAGS) -c $< -o $@

# Link into ELF
$(ELF): $(OBJS)
	@mkdir -p $(BUILD)
	$(CC) $(OBJS) $(LDFLAGS) $(LIBS) -o $@

# Convert ELF -> exefs/main (NSO)
$(NSO): $(ELF)
	@mkdir -p $(EXEFSDIR)
	$(ELF2NSO) $< $@

# Build exefs/main.npdm from JSON
$(NPDM): $(NPDM_JSON)
	@mkdir -p $(EXEFSDIR)
	$(NPDMTOOL) $< $@

# Where to copy the built ExeFS for consumers (packer, stub, etc.)
VENDOR_EXEFS ?= $(CURDIR)/../stub/vendor/exefs

.PHONY: install
install: all
	@mkdir -p $(VENDOR_EXEFS)
	cp -f $(EXEFSDIR)/main $(VENDOR_EXEFS)/main
	cp -f $(EXEFSDIR)/main.npdm $(VENDOR_EXEFS)/main.npdm
	@echo "Installed exefs to $(VENDOR_EXEFS)"

clean:
	@rm -rf $(BUILD) $(OUTDIR)

# Debug: print flags
print-vars:
	@echo "CC=$(CC)"
	@echo "CFLAGS=$(CFLAGS)"
	@echo "CPPFLAGS=$(CPPFLAGS)"
	@echo "LDFLAGS=$(LDFLAGS)"
	@echo "LIBS=$(LIBS)"
