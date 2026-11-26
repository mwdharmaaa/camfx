# Makefile for CamFX Debian Packaging

APP_NAME = camfx
VERSION = $(shell python3 -c "import camfx; print(camfx.__version__)")
STAGE_DIR = dist-deb/$(APP_NAME)_$(VERSION)_amd64
OUTPUT_DIR = output/deb
DEB_FILE = $(OUTPUT_DIR)/$(APP_NAME)_$(VERSION)_amd64.deb

.PHONY: all clean icons test package distribute install

all: distribute

clean:
	@echo "Cleaning up old builds..."
	@rm -rf dist-deb $(OUTPUT_DIR)

icons:
	@echo "Generating application icons..."
	@python3 scripts/generate_icon.py >/dev/null

test:
	@echo "Running CamFX test suite..."
	@PYTHONPATH=. python3 -m unittest discover -s tests -v

package: clean icons
	@echo "Staging Debian package $(DEB_FILE)..."
	@mkdir -p $(STAGE_DIR)/DEBIAN \
		$(STAGE_DIR)/usr/lib/$(APP_NAME) \
		$(STAGE_DIR)/usr/bin \
		$(STAGE_DIR)/usr/share/applications \
		$(STAGE_DIR)/etc/modules-load.d \
		$(STAGE_DIR)/etc/modprobe.d \
		$(OUTPUT_DIR)

	@cp -r camfx $(STAGE_DIR)/usr/lib/$(APP_NAME)/
	@find $(STAGE_DIR)/usr/lib/$(APP_NAME) -name "__pycache__" -exec rm -rf {} +

	@for s in 16 32 48 64 128 256; do \
		mkdir -p $(STAGE_DIR)/usr/share/icons/hicolor/$${s}x$${s}/apps; \
		cp assets/logo/logo-$${s}.png $(STAGE_DIR)/usr/share/icons/hicolor/$${s}x$${s}/apps/$(APP_NAME).png; \
	done
	@mkdir -p $(STAGE_DIR)/usr/share/icons/hicolor/512x512/apps
	@cp assets/logo/logo.png $(STAGE_DIR)/usr/share/icons/hicolor/512x512/apps/$(APP_NAME).png

	@printf '%s\n' \
		'#!/bin/bash' \
		'LOG_DIR="$${XDG_STATE_HOME:-$$HOME/.local/state}/camfx"' \
		'mkdir -p "$$LOG_DIR" && chmod 700 "$$LOG_DIR"' \
		'export PYTHONPATH="/usr/lib/camfx$${PYTHONPATH:+:$$PYTHONPATH}"' \
		'for arg in "$$@"; do' \
		'  case "$$arg" in' \
		'    -v|--version|-h|--help|--list-effects|--list-devices|--headless)' \
		'      exec python3 -m camfx.cli "$$@"' \
		'      ;;' \
		'    --log-path)' \
		'      echo "$$LOG_DIR/camfx.log"' \
		'      exit 0' \
		'      ;;' \
		'    -l|--log|--logs)' \
		'      if [[ "$$*" == *"-f"* || "$$*" == *"--follow"* ]]; then' \
		'        exec tail -n 50 -f "$$LOG_DIR/camfx.log"' \
		'      else' \
		'        exec tail -n 50 "$$LOG_DIR/camfx.log"' \
		'      fi' \
		'      ;;' \
		'  esac' \
		'done' \
		'touch "$$LOG_DIR/camfx.log" && chmod 600 "$$LOG_DIR/camfx.log"' \
		'nohup python3 -m camfx.cli "$$@" </dev/null >>"$$LOG_DIR/camfx.log" 2>&1 &' \
		> $(STAGE_DIR)/usr/bin/$(APP_NAME)
	@chmod 755 $(STAGE_DIR)/usr/bin/$(APP_NAME)

	@printf '%s\n' \
		'[Desktop Entry]' \
		'Name=CamFX' \
		'GenericName=Custom Effect Virtual Camera' \
		'Comment=Custom virtual camera with real-time GLSL shaders, Studio HUD, and v4l2loopback output' \
		'Exec=/usr/bin/camfx %U' \
		'Icon=camfx' \
		'Terminal=false' \
		'Type=Application' \
		'Categories=AudioVideo;Video;' \
		'StartupWMClass=dev.camfx.CamFX' \
		> $(STAGE_DIR)/usr/share/applications/$(APP_NAME).desktop
	@chmod 644 $(STAGE_DIR)/usr/share/applications/$(APP_NAME).desktop

	@echo "v4l2loopback" > $(STAGE_DIR)/etc/modules-load.d/$(APP_NAME).conf
	@echo 'options v4l2loopback devices=1 video_nr=10 card_label="CamFX Virtual Camera" exclusive_caps=1' > $(STAGE_DIR)/etc/modprobe.d/$(APP_NAME).conf

	@printf '%s\n' \
		'Package: $(APP_NAME)' \
		'Version: $(VERSION)' \
		'Section: video' \
		'Priority: optional' \
		'Architecture: amd64' \
		'Maintainer: CamFX <camfx@local>' \
		'Depends: python3, python3-gi, python3-pil, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gstreamer-1.0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-gl, gstreamer1.0-gtk4' \
		'Description: Custom Effect Virtual Camera for Linux' \
		' Real-time camera effects studio (GLSL shaders, EffecTV, Studio HUD)' \
		' with v4l2loopback virtual camera output for Zoom, Meet, Chrome, and OBS.' \
		> $(STAGE_DIR)/DEBIAN/control

	@printf '%s\n' \
		'#!/bin/bash' \
		'set -e' \
		'if ! lsmod | grep -q "^v4l2loopback"; then' \
		'  modprobe v4l2loopback devices=1 video_nr=10 card_label="CamFX Virtual Camera" exclusive_caps=1 || true' \
		'fi' \
		'if command -v update-desktop-database >/dev/null 2>&1; then' \
		'  update-desktop-database -q || true' \
		'fi' \
		'if command -v gtk-update-icon-cache >/dev/null 2>&1; then' \
		'  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true' \
		'fi' \
		> $(STAGE_DIR)/DEBIAN/postinst
	@chmod 755 $(STAGE_DIR)/DEBIAN/postinst

	@printf '%s\n' \
		'#!/bin/bash' \
		'set -e' \
		'if command -v update-desktop-database >/dev/null 2>&1; then' \
		'  update-desktop-database -q || true' \
		'fi' \
		'if command -v gtk-update-icon-cache >/dev/null 2>&1; then' \
		'  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true' \
		'fi' \
		> $(STAGE_DIR)/DEBIAN/postrm
	@chmod 755 $(STAGE_DIR)/DEBIAN/postrm

	@dpkg-deb --build --root-owner-group $(STAGE_DIR) $(DEB_FILE) >/dev/null
	@echo "Built $(DEB_FILE) ($$(du -h $(DEB_FILE) | cut -f1))"

distribute: package
	@echo "Package generated at $(DEB_FILE)"

install: package
	@sudo apt install -y --reinstall ./$(DEB_FILE)
