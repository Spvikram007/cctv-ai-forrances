"""
Professional Dark Surveillance Theme for PySide6.
Optimized for low-light command center environments, high contrast,
and low cognitive load during 24/7 security surveillance.
"""

DARK_THEME_QSS = """
/* Global Window & Typography */
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
    font-size: 13px;
}

/* Header Container */
#HeaderWidget {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 6px 16px;
}

#AppTitleLabel {
    font-size: 16px;
    font-weight: 700;
    color: #58a6ff;
    letter-spacing: 0.5px;
}

#ClockLabel {
    font-size: 13px;
    font-weight: 600;
    color: #8b949e;
    padding-right: 12px;
}

#BadgeIntel {
    background-color: #0071c5;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 4px;
}

#BadgeAlarm {
    background-color: #f85149;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 4px;
}

#BadgeHealthy {
    background-color: #238636;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 4px;
}

/* Sidebar Navigation */
#SidebarWidget {
    background-color: #161b22;
    border-right: 1px solid #30363d;
    min-width: 210px;
    max-width: 210px;
}

QPushButton.nav-btn {
    text-align: left;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 500;
    color: #c9d1d9;
    background-color: transparent;
    border: none;
    border-radius: 6px;
    margin: 2px 8px;
}

QPushButton.nav-btn:hover {
    background-color: #21262d;
    color: #58a6ff;
}

QPushButton.nav-btn:checked, QPushButton.nav-btn.active {
    background-color: #1f6feb;
    color: #ffffff;
    font-weight: 600;
}

/* Content Area & Cards */
#ContentArea {
    background-color: #0d1117;
}

QFrame.card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
}

QFrame.card:hover {
    border: 1px solid #58a6ff;
}

QLabel.card-title {
    font-size: 12px;
    font-weight: 600;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

QLabel.card-value {
    font-size: 26px;
    font-weight: 700;
    color: #f0f6fc;
    margin-top: 4px;
}

QLabel.card-subtext {
    font-size: 11px;
    color: #7d8590;
    margin-top: 2px;
}

/* Progress Bars */
QProgressBar {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
    color: #f0f6fc;
    font-size: 11px;
    font-weight: 600;
    height: 14px;
}

QProgressBar::chunk {
    background-color: #1f6feb;
    border-radius: 3px;
}

QProgressBar.warning::chunk {
    background-color: #d29922;
}

QProgressBar.critical::chunk {
    background-color: #f85149;
}

/* Tables & Lists */
QTableWidget, QTreeWidget, QListWidget {
    background-color: #161b22;
    alternate-background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    gridline-color: #21262d;
    color: #c9d1d9;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #21262d;
    color: #8b949e;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid #30363d;
    padding: 6px 10px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #0d1117;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: #58a6ff;
}

/* Status Bar */
QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #30363d;
    color: #8b949e;
    font-size: 12px;
    padding: 4px 12px;
}
"""
