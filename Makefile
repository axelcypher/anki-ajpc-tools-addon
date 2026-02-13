PYTHON ?= python

.PHONY: help vendor vendor-all vendor-win vendor-linux vendor-macos-x64 vendor-macos-arm64 vendor-check vendor-clean

help:
	@echo "Targets:"
	@echo "  make vendor           - install vendor for local platform + common"
	@echo "  make vendor-all       - install vendor for win/linux/macos_x86_64/macos_arm64 + common"
	@echo "  make vendor-win       - install vendor/win + common"
	@echo "  make vendor-linux     - install vendor/linux + common"
	@echo "  make vendor-macos-x64 - install vendor/macos_x86_64 + common"
	@echo "  make vendor-macos-arm64 - install vendor/macos_arm64 + common"
	@echo "  make vendor-check     - check vendor files for local platform"
	@echo "  make vendor-clean     - remove local vendor and temp wheel cache"

vendor:
	$(PYTHON) scripts/bootstrap_vendor.py --target local

vendor-all:
	$(PYTHON) scripts/bootstrap_vendor.py --target all

vendor-win:
	$(PYTHON) scripts/bootstrap_vendor.py --target win

vendor-linux:
	$(PYTHON) scripts/bootstrap_vendor.py --target linux

vendor-macos-x64:
	$(PYTHON) scripts/bootstrap_vendor.py --target macos_x86_64

vendor-macos-arm64:
	$(PYTHON) scripts/bootstrap_vendor.py --target macos_arm64

vendor-check:
	$(PYTHON) scripts/bootstrap_vendor.py --target local --check-only

vendor-clean:
	$(PYTHON) scripts/bootstrap_vendor.py --clean
