# Sacred Brain installer
#
# Common targets:
#   sudo make install           Full install (user, dirs, package, units, configs)
#   sudo make install-update    Reinstall package + units, restart services
#   sudo make uninstall         Stop + disable + remove units (keeps state)
#   sudo make uninstall-purge   Also remove configs, state, and 'sacred' user
#
# Honors DESTDIR, PREFIX, SYSCONFDIR, PIPX_HOME for packagers and non-default
# installs:
#   make install PREFIX=/usr SYSCONFDIR=/etc DESTDIR=/tmp/stage

PREFIX     ?= /usr/local
SYSCONFDIR ?= /etc
DESTDIR    ?=

ETC_DIR     := $(DESTDIR)$(SYSCONFDIR)/sacred-brain
STATE_DIR   := $(DESTDIR)/var/lib/sacred-brain
SYSTEMD_DIR := $(DESTDIR)/etc/systemd/system
BIN_DIR     := $(DESTDIR)$(PREFIX)/bin

# pipx layout: a system-wide venv under /opt/pipx, with bins symlinked into
# $(PREFIX)/bin. This works on every pipx version (no --global needed) and
# keeps service binaries on the standard PATH.
PIPX_HOME    ?= /opt/pipx
PIPX_BIN_DIR ?= $(PREFIX)/bin

REPO_DIR := $(shell pwd)

.PHONY: install install-update install-deps migrate-legacy install-package \
        install-bin install-systemd install-config uninstall uninstall-purge help

help:
	@sed -n '1,12p' Makefile

# ── Composite targets ───────────────────────────────────────────────

install: install-deps migrate-legacy install-package install-bin install-systemd install-config
	@./scripts/post-install-message.sh "$(ETC_DIR)" || true

# Auto-cleanup of pre-pipx layout. Older installs put the venv at
# /opt/sacred-brain/.venv and the systemd ExecStarts pointed there. After
# this install, those paths are dead weight (and could confuse a future
# `pip install -e` if anyone runs it). Idempotent — silent if already clean.
migrate-legacy:
	@if [ -d /opt/sacred-brain/.venv ]; then \
	    echo "  [+] Removing legacy in-tree venv: /opt/sacred-brain/.venv"; \
	    rm -rf /opt/sacred-brain/.venv; \
	fi
	@if [ -e /opt/sacred-brain/.venv ]; then \
	    echo "  [!] /opt/sacred-brain/.venv still present after cleanup — investigate"; \
	fi

install-update: install-package install-systemd
	systemctl daemon-reload
	@for unit in $$(ls ops/systemd/*.service | xargs -n1 basename); do \
	    systemctl is-enabled $$unit >/dev/null 2>&1 && systemctl restart $$unit || true; \
	done

# ── Phase: service user + state dirs ────────────────────────────────

install-deps:
	@if ! id sacred >/dev/null 2>&1; then \
	    echo "  [+] Creating service user 'sacred'"; \
	    useradd --system --shell /usr/sbin/nologin --home-dir /opt/sacred-brain sacred; \
	else echo "  [+] User 'sacred' already exists"; fi
	@echo "  [+] Creating state directories"
	install -d -m 0755 -o sacred -g sacred $(STATE_DIR)/hippocampus
	install -d -m 0755 -o sacred -g sacred $(STATE_DIR)/governor
	install -d -m 0755 -o sacred -g sacred $(STATE_DIR)/cache
	install -d -m 0755 -o sacred -g sacred $(ETC_DIR)

# ── Phase: Python package via pipx ──────────────────────────────────

install-package:
	@command -v pipx >/dev/null || { echo "ERROR: pipx not installed (apt install pipx)"; exit 1; }
	@echo "  [+] Installing Python package via pipx into $(PIPX_HOME)"
	PIPX_HOME=$(PIPX_HOME) PIPX_BIN_DIR=$(PIPX_BIN_DIR) \
	    pipx install --force "$(REPO_DIR)"

# ── Phase: shell scripts on PATH ────────────────────────────────────

install-bin:
	@echo "  [+] Installing shell utilities to $(BIN_DIR)"
	install -d -m 0755 $(BIN_DIR)
	install -m 0755 scripts/sacred-search $(BIN_DIR)/sacred-search

# ── Phase: systemd units ────────────────────────────────────────────

install-systemd:
	@echo "  [+] Installing systemd units to $(SYSTEMD_DIR)"
	install -d -m 0755 $(SYSTEMD_DIR)
	@for f in ops/systemd/*.service ops/systemd/*.timer; do \
	    [ -e "$$f" ] || continue; \
	    install -m 0644 "$$f" $(SYSTEMD_DIR)/; \
	    echo "      $$(basename $$f)"; \
	done
	@if [ -z "$(DESTDIR)" ]; then \
	    systemctl daemon-reload; \
	    for f in ops/systemd/*.service ops/systemd/*.timer; do \
	        [ -e "$$f" ] || continue; \
	        if grep -q '^\[Install\]' "$$f"; then \
	            systemctl enable "$$(basename $$f)"; \
	        fi; \
	    done; \
	fi

# ── Phase: config templates ─────────────────────────────────────────

install-config:
	@echo "  [+] Installing config templates to $(ETC_DIR)"
	@for tmpl in ops/config/*.example; do \
	    [ -e "$$tmpl" ] || continue; \
	    target="$(ETC_DIR)/$$(basename $${tmpl%.example})"; \
	    if [ -f "$$target" ]; then \
	        echo "      exists, skipping: $$target"; \
	    else \
	        install -m 0640 -o sacred -g sacred "$$tmpl" "$$target"; \
	        echo "      created: $$target  (edit CHANGE_ME values!)"; \
	    fi; \
	done

# ── Uninstall ───────────────────────────────────────────────────────

uninstall:
	@echo "  [+] Stopping and disabling units"
	@for f in ops/systemd/*.service ops/systemd/*.timer; do \
	    [ -e "$$f" ] || continue; \
	    unit=$$(basename $$f); \
	    if [ -f "$(SYSTEMD_DIR)/$$unit" ]; then \
	        systemctl disable --now "$$unit" 2>/dev/null || true; \
	        rm -f "$(SYSTEMD_DIR)/$$unit"; \
	    fi; \
	done
	@if [ -z "$(DESTDIR)" ]; then systemctl daemon-reload; fi
	@echo "  [+] Removing $(BIN_DIR)/sacred-search"
	@rm -f $(BIN_DIR)/sacred-search
	@echo "  [+] Uninstalling Python package"
	@PIPX_HOME=$(PIPX_HOME) PIPX_BIN_DIR=$(PIPX_BIN_DIR) \
	    pipx uninstall sacred-brain-hippocampus 2>/dev/null || true
	@echo "  [+] Kept $(ETC_DIR) and $(STATE_DIR) (use 'make uninstall-purge' to remove)"

uninstall-purge: uninstall
	@echo "  [+] Removing $(ETC_DIR) and $(STATE_DIR)"
	rm -rf $(ETC_DIR) $(STATE_DIR)
	@if id sacred >/dev/null 2>&1; then \
	    echo "  [+] Removing service user 'sacred'"; \
	    userdel sacred 2>/dev/null || echo "  [!] could not remove user 'sacred'"; \
	fi
