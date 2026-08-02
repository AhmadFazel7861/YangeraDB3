/**
 * فروشگاه موادغذایی حسیب فیاض — ERP Main JavaScript
 * Designer: YangEra
 * Offline — no external dependencies
 */

'use strict';

// ─── THEME SYSTEM ─────────────────────────────────────────────
const ThemeManager = {
  STORAGE_KEY: 'erp_theme',
  DEFAULT: 'light',

  init() {
    const saved = localStorage.getItem(this.STORAGE_KEY) || this.DEFAULT;
    this.apply(saved);
    this.bindToggle();
  },

  apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(this.STORAGE_KEY, theme);

    const btn = document.getElementById('themeToggleBtn');
    if (btn) {
      const icon = btn.querySelector('i');
      const label = btn.querySelector('.theme-label');
      if (theme === 'dark') {
        if (icon) { icon.className = 'bi bi-sun-fill'; }
        if (label) label.textContent = 'روز';
      } else {
        if (icon) { icon.className = 'bi bi-moon-fill'; }
        if (label) label.textContent = 'شب';
      }
    }
  },

  toggle() {
    const current = document.documentElement.getAttribute('data-theme') || this.DEFAULT;
    this.apply(current === 'dark' ? 'light' : 'dark');
  },

  bindToggle() {
    const btn = document.getElementById('themeToggleBtn');
    if (btn) btn.addEventListener('click', () => this.toggle());
  }
};

// ─── SIDEBAR SYSTEM ───────────────────────────────────────────
const SidebarManager = {
  STORAGE_KEY: 'erp_sidebar_collapsed',
  sidebar: null,
  overlay: null,
  isMobile: false,

  init() {
    this.sidebar = document.getElementById('erpSidebar');
    this.overlay = document.getElementById('sidebarOverlay');
    this.isMobile = window.innerWidth <= 768;

    if (!this.sidebar) return;

    // Restore desktop collapse state
    if (!this.isMobile) {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      if (saved === 'true') {
        this.sidebar.classList.add('collapsed');
      }
    }

    // Bind toggle button
    const toggleBtn = document.getElementById('sidebarToggleBtn');
    if (toggleBtn) toggleBtn.addEventListener('click', () => this.toggle());

    // Bind overlay close
    if (this.overlay) {
      this.overlay.addEventListener('click', () => this.closeMobile());
    }

    // Bind submenu items
    this.initSubmenus();

    // Responsive listener
    window.addEventListener('resize', () => {
      this.isMobile = window.innerWidth <= 768;
    });
  },

  toggle() {
    if (this.isMobile) {
      this.toggleMobile();
    } else {
      this.toggleDesktop();
    }
  },

  toggleDesktop() {
    const collapsed = this.sidebar.classList.toggle('collapsed');
    localStorage.setItem(this.STORAGE_KEY, collapsed);
  },

  toggleMobile() {
    const isOpen = this.sidebar.classList.toggle('mobile-open');
    if (this.overlay) {
      this.overlay.classList.toggle('active', isOpen);
    }
    document.body.style.overflow = isOpen ? 'hidden' : '';
  },

  closeMobile() {
    this.sidebar.classList.remove('mobile-open');
    if (this.overlay) this.overlay.classList.remove('active');
    document.body.style.overflow = '';
  },

  initSubmenus() {
    const parentItems = document.querySelectorAll('.nav-parent');

    parentItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();

        // The submenu is the next .nav-submenu sibling of the parent wrapper div
        const wrapper = item.closest('.nav-item-wrapper');
        const submenuWrapper = wrapper ? wrapper.nextElementSibling : null;
        const submenu = submenuWrapper && submenuWrapper.classList.contains('nav-submenu')
          ? submenuWrapper
          : null;

        const arrow = item.querySelector('.nav-arrow');
        const menuId = item.dataset.menuId;

        if (submenu) {
          const isOpen = submenu.classList.toggle('open');
          if (arrow) arrow.classList.toggle('rotated', isOpen);
          if (menuId) {
            localStorage.setItem(`erp_menu_${menuId}`, isOpen);
          }
        }
      });
    });

    // Restore open states from localStorage
    document.querySelectorAll('.nav-parent[data-menu-id]').forEach(item => {
      const menuId = item.dataset.menuId;
      const isOpen = localStorage.getItem(`erp_menu_${menuId}`) === 'true';
      if (isOpen) {
        const wrapper = item.closest('.nav-item-wrapper');
        const submenuWrapper = wrapper ? wrapper.nextElementSibling : null;
        if (submenuWrapper && submenuWrapper.classList.contains('nav-submenu')) {
          submenuWrapper.classList.add('open');
          const arrow = item.querySelector('.nav-arrow');
          if (arrow) arrow.classList.add('rotated');
        }
      }
    });
  }
};

// ─── ALERT AUTO-DISMISS ───────────────────────────────────────
const AlertManager = {
  init() {
    const alerts = document.querySelectorAll('.erp-alert[data-auto-dismiss]');
    alerts.forEach(alert => {
      const delay = parseInt(alert.dataset.autoDismiss) || 4000;
      setTimeout(() => {
        alert.style.transition = 'opacity 0.4s ease, max-height 0.4s ease';
        alert.style.opacity = '0';
        alert.style.maxHeight = '0';
        alert.style.overflow = 'hidden';
        alert.style.marginBottom = '0';
        alert.style.padding = '0';
        setTimeout(() => alert.remove(), 450);
      }, delay);
    });

    // Manual close buttons
    document.querySelectorAll('.erp-alert .close-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const alert = btn.closest('.erp-alert');
        if (alert) alert.remove();
      });
    });
  }
};

// ─── ACTIVE NAV DETECTION ─────────────────────────────────────
const NavHighlighter = {
  init() {
    const path = window.location.pathname;
    const links = document.querySelectorAll('.nav-link-item[href]');

    links.forEach(link => {
      const href = link.getAttribute('href');
      if (href && href !== '#' && path.startsWith(href) && href !== '/') {
        link.classList.add('active');
        // Open parent submenu if this child is active
        const submenu = link.closest('.nav-submenu');
        if (submenu) {
          submenu.classList.add('open');
          const parent = submenu.previousElementSibling?.querySelector('.nav-parent');
          if (parent) {
            const arrow = parent.querySelector('.nav-arrow');
            if (arrow) arrow.classList.add('rotated');
          }
        }
      }
    });

    // Dashboard exact match
    if (path === '/dashboard/' || path === '/dashboard') {
      const dashLink = document.querySelector('.nav-link-item[href="/dashboard/"]');
      if (dashLink) dashLink.classList.add('active');
    }
  }
};

// ─── KEYBOARD SHORTCUTS ───────────────────────────────────────
const KeyboardManager = {
  init() {
    document.addEventListener('keydown', (e) => {
      // Alt + S = toggle sidebar
      if (e.altKey && e.key === 's') {
        e.preventDefault();
        SidebarManager.toggle();
      }
      // Alt + T = toggle theme
      if (e.altKey && e.key === 't') {
        e.preventDefault();
        ThemeManager.toggle();
      }
      // ESC = close mobile sidebar
      if (e.key === 'Escape') {
        SidebarManager.closeMobile();
      }
    });
  }
};

// ─── INITIALIZE ALL ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  ThemeManager.init();
  SidebarManager.init();
  AlertManager.init();
  NavHighlighter.init();
  KeyboardManager.init();

  // Fade-in content
  const content = document.querySelector('.erp-content');
  if (content) content.classList.add('fade-in');
});