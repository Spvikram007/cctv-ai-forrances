"""
User Management and RBAC Administration Workspace Widget (Phase 14 - Module A & B).
Implements complete user lifecycle administration, permission matrix inspection,
account lockout unlocking, and active session monitoring.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QLineEdit, QComboBox, QMessageBox, QFrame, QSplitter,
    QInputDialog, QTreeWidget, QTreeWidgetItem
)

from core.logging.logger import get_logger
from core.security.user_service import user_service
from core.security.rbac import rbac_service, ALL_PERMISSIONS
from modules.user_management.user_dialog import UserDialog

logger = get_logger("user_management_widget")


class UserManagementWidget(QWidget):
    """Primary Command Center Workspace for Users, Roles, and Sessions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._cached_users: List[Dict[str, Any]] = []
        self._cached_roles: List[Dict[str, Any]] = []
        self._init_ui()
        self._load_data()

    def _init_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # 1. Top Header & KPI Telemetry Cards
        header_layout = QHBoxLayout()
        lbl_title = QLabel("USER MANAGEMENT & ROLE-BASED ACCESS CONTROL")
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #58a6ff;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        self.btn_refresh = QPushButton("Refresh Data")
        self.btn_refresh.clicked.connect(self._load_data)
        header_layout.addWidget(self.btn_refresh)
        root_layout.addLayout(header_layout)

        # KPI Summary Cards
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(10)

        self.card_total = self._create_kpi_card("TOTAL USERS", "0", "#58a6ff")
        self.card_active = self._create_kpi_card("ACTIVE ACCOUNTS", "0", "#2ea043")
        self.card_locked = self._create_kpi_card("LOCKED ACCOUNTS", "0", "#f85149")
        self.card_sessions = self._create_kpi_card("ACTIVE SESSIONS", "0", "#d29922")

        kpi_layout.addWidget(self.card_total)
        kpi_layout.addWidget(self.card_active)
        kpi_layout.addWidget(self.card_locked)
        kpi_layout.addWidget(self.card_sessions)
        root_layout.addLayout(kpi_layout)

        # 2. Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #0d1117; }
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 16px; border: 1px solid #30363d; }
            QTabBar::tab:selected { background: #0d1117; color: #58a6ff; font-weight: bold; border-bottom: 2px solid #58a6ff; }
        """)

        # Tab 1: Users Table
        self.tab_users = self._create_users_tab()
        self.tabs.addTab(self.tab_users, "User Accounts")

        # Tab 2: Roles & Permissions Matrix
        self.tab_roles = self._create_roles_tab()
        self.tabs.addTab(self.tab_roles, "Roles & Permissions Matrix")

        # Tab 3: Active Sessions
        self.tab_sessions = self._create_sessions_tab()
        self.tabs.addTab(self.tab_sessions, "Active Operator Sessions")

        root_layout.addWidget(self.tabs, stretch=1)

    def _create_kpi_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px;")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 8pt; color: #8b949e; font-weight: bold;")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 16pt; font-weight: bold; color: {color};")
        lbl_v.setObjectName("val")

        layout.addWidget(lbl_t)
        layout.addWidget(lbl_v)
        return card

    def _update_kpi_card(self, card: QFrame, value: str) -> None:
        lbl_v = card.findChild(QLabel, "val")
        if lbl_v:
            lbl_v.setText(str(value))

    def _create_users_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Action / Filter Bar
        bar = QHBoxLayout()
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Search users by username, name, or role...")
        self.txt_search.textChanged.connect(self._filter_users_table)
        bar.addWidget(self.txt_search, stretch=1)

        self.combo_role_filter = QComboBox()
        self.combo_role_filter.addItem("All Roles", "ALL")
        self.combo_role_filter.currentIndexChanged.connect(self._filter_users_table)
        bar.addWidget(self.combo_role_filter)

        self.btn_new_user = QPushButton("+ New User Account")
        self.btn_new_user.setStyleSheet("background-color: #238636; color: #fff; font-weight: bold; padding: 6px 14px;")
        self.btn_new_user.clicked.connect(self._open_new_user_dialog)
        bar.addWidget(self.btn_new_user)

        layout.addLayout(bar)

        # Table
        self.table_users = QTableWidget()
        self.table_users.setColumnCount(8)
        self.table_users.setHorizontalHeaderLabels([
            "Username", "Full Name", "Assigned Role", "Email", "Status",
            "Failed Attempts", "Last Login", "Actions"
        ])
        self.table_users.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_users.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table_users.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_users.setAlternatingRowColors(True)
        self.table_users.setStyleSheet("""
            QTableWidget { background-color: #0d1117; color: #c9d1d9; gridline-color: #30363d; }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background-color: #1f6feb; }
            QHeaderView::section { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; padding: 6px; font-weight: bold; }
        """)
        layout.addWidget(self.table_users, stretch=1)
        return widget

    def _create_roles_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Horizontal)

        # Left: Roles List
        left_panel = QFrame()
        left_panel.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 4px;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)

        lbl_roles = QLabel("SURVEILLANCE ROLES (10 STANDARD)")
        lbl_roles.setStyleSheet("font-weight: bold; color: #58a6ff; font-size: 10pt; margin-bottom: 6px;")
        left_layout.addWidget(lbl_roles)

        self.table_roles = QTableWidget()
        self.table_roles.setColumnCount(3)
        self.table_roles.setHorizontalHeaderLabels(["Role Name", "Type", "Users"])
        self.table_roles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_roles.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_roles.setAlternatingRowColors(True)
        self.table_roles.itemSelectionChanged.connect(self._on_role_selected)
        left_layout.addWidget(self.table_roles)
        splitter.addWidget(left_panel)

        # Right: Permissions Tree for Selected Role
        right_panel = QFrame()
        right_panel.setStyleSheet("background: #161b22; border: 1px solid #30363d; border-radius: 4px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_selected_role = QLabel("PERMISSIONS FOR: [Select a Role]")
        self.lbl_selected_role.setStyleSheet("font-weight: bold; color: #58a6ff; font-size: 10pt; margin-bottom: 6px;")
        right_layout.addWidget(self.lbl_selected_role)

        self.tree_permissions = QTreeWidget()
        self.tree_permissions.setHeaderLabels(["Permission / Subsystem Capability", "Scope Code", "Status"])
        self.tree_permissions.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_permissions.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_permissions.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_permissions.setStyleSheet("""
            QTreeWidget { background-color: #0d1117; color: #c9d1d9; border: 1px solid #30363d; }
            QTreeWidget::item { padding: 4px; }
            QHeaderView::section { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; padding: 4px; }
        """)
        right_layout.addWidget(self.tree_permissions)
        splitter.addWidget(right_panel)

        splitter.setSizes([350, 600])
        layout.addWidget(splitter)
        return widget

    def _create_sessions_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        self.table_sessions = QTableWidget()
        self.table_sessions.setColumnCount(7)
        self.table_sessions.setHorizontalHeaderLabels([
            "Session ID", "Username", "Role", "IP Address", "User Agent", "Expires At", "Action"
        ])
        self.table_sessions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_sessions.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_sessions.setAlternatingRowColors(True)
        layout.addWidget(self.table_sessions)
        return widget

    def _load_data(self) -> None:
        """Reloads users, roles, and sessions from the database."""
        try:
            self._cached_users = user_service.list_users()
            self._cached_roles = rbac_service.get_all_roles()
            active_sessions = user_service.list_active_sessions()

            # Update KPIs
            total_users = len(self._cached_users)
            active_users = sum(1 for u in self._cached_users if u.get("is_active") and not u.get("is_locked"))
            locked_users = sum(1 for u in self._cached_users if u.get("is_locked"))

            self._update_kpi_card(self.card_total, str(total_users))
            self._update_kpi_card(self.card_active, str(active_users))
            self._update_kpi_card(self.card_locked, str(locked_users))
            self._update_kpi_card(self.card_sessions, str(len(active_sessions)))

            # Populate Role Filter dropdown
            self.combo_role_filter.blockSignals(True)
            self.combo_role_filter.clear()
            self.combo_role_filter.addItem("All Roles", "ALL")
            for r in self._cached_roles:
                self.combo_role_filter.addItem(r["name"], r["id"])
            self.combo_role_filter.blockSignals(False)

            self._populate_users_table(self._cached_users)
            self._populate_roles_table(self._cached_roles)
            self._populate_sessions_table(active_sessions)
        except Exception as e:
            logger.error("Failed to load user management data: %s", e)

    def _populate_users_table(self, users: List[Dict[str, Any]]) -> None:
        self.table_users.setRowCount(len(users))
        for row, u in enumerate(users):
            self.table_users.setItem(row, 0, QTableWidgetItem(u.get("username", "")))
            self.table_users.setItem(row, 1, QTableWidgetItem(u.get("full_name", "")))
            self.table_users.setItem(row, 2, QTableWidgetItem(u.get("role_name", "")))
            self.table_users.setItem(row, 3, QTableWidgetItem(u.get("email", "") or "-"))

            # Status pill
            is_locked = u.get("is_locked")
            is_active = u.get("is_active")
            if is_locked:
                status_text = "LOCKED"
                status_color = QColor("#f85149")
            elif is_active:
                status_text = "ACTIVE"
                status_color = QColor("#2ea043")
            else:
                status_text = "INACTIVE"
                status_color = QColor("#8b949e")

            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(status_color)
            item_status.setFont(QFont("Arial", 9, QFont.Bold))
            self.table_users.setItem(row, 4, item_status)

            self.table_users.setItem(row, 5, QTableWidgetItem(str(u.get("failed_attempts", 0))))
            self.table_users.setItem(row, 6, QTableWidgetItem(u.get("last_login_at", "Never")[:19] if u.get("last_login_at") else "Never"))

            # Actions Cell
            actions_widget = QWidget()
            act_layout = QHBoxLayout(actions_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(4)

            btn_edit = QPushButton("Edit")
            btn_edit.clicked.connect(lambda _, uid=u["id"]: self._edit_user(uid))
            act_layout.addWidget(btn_edit)

            if is_locked:
                btn_unlock = QPushButton("Unlock")
                btn_unlock.setStyleSheet("color: #f85149; font-weight: bold;")
                btn_unlock.clicked.connect(lambda _, uid=u["id"]: self._unlock_user(uid))
                act_layout.addWidget(btn_unlock)

            btn_pwd = QPushButton("Reset Pwd")
            btn_pwd.clicked.connect(lambda _, uid=u["id"]: self._admin_reset_password(uid))
            act_layout.addWidget(btn_pwd)

            self.table_users.setCellWidget(row, 7, actions_widget)

    def _filter_users_table(self) -> None:
        search = self.txt_search.text().lower().strip()
        role_filter = self.combo_role_filter.currentData()

        filtered = []
        for u in self._cached_users:
            if role_filter != "ALL" and u.get("role_id") != role_filter:
                continue
            if search:
                match = (
                    search in u.get("username", "").lower() or
                    search in u.get("full_name", "").lower() or
                    search in u.get("role_name", "").lower() or
                    search in (u.get("email") or "").lower()
                )
                if not match:
                    continue
            filtered.append(u)
        self._populate_users_table(filtered)

    def _populate_roles_table(self, roles: List[Dict[str, Any]]) -> None:
        self.table_roles.setRowCount(len(roles))
        for row, r in enumerate(roles):
            self.table_roles.setItem(row, 0, QTableWidgetItem(r.get("name", "")))
            type_text = "System Role" if r.get("is_system") else "Custom"
            item_type = QTableWidgetItem(type_text)
            item_type.setForeground(QColor("#58a6ff") if r.get("is_system") else QColor("#d29922"))
            self.table_roles.setItem(row, 1, item_type)
            self.table_roles.setItem(row, 2, QTableWidgetItem(str(r.get("user_count", 0))))

        if roles:
            self.table_roles.selectRow(0)

    def _on_role_selected(self) -> None:
        selected_rows = self.table_roles.selectedItems()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if row < len(self._cached_roles):
            role = self._cached_roles[row]
            self.lbl_selected_role.setText(f"PERMISSIONS FOR: {role['name'].upper()} ({len(role['permissions'])} Active)")
            self._populate_permissions_tree(role["permissions"])

    def _populate_permissions_tree(self, role_permissions: List[Dict[str, Any]]) -> None:
        self.tree_permissions.clear()
        assigned_codes = {p["code"] for p in role_permissions}

        # Group all 22 permissions by category
        categories: Dict[str, List] = {}
        for code, name, module, desc in ALL_PERMISSIONS:
            categories.setdefault(module.upper(), []).append((code, name, desc))

        for cat, perms in categories.items():
            cat_item = QTreeWidgetItem([cat, "", ""])
            cat_item.setFont(0, QFont("Arial", 9, QFont.Bold))
            cat_item.setForeground(0, QColor("#58a6ff"))

            for code, name, desc in perms:
                has_perm = code in assigned_codes
                status_text = "GRANTED" if has_perm else "DENIED"
                status_color = QColor("#2ea043") if has_perm else QColor("#484f58")

                child = QTreeWidgetItem([name, code, status_text])
                child.setForeground(2, status_color)
                child.setFont(2, QFont("Arial", 9, QFont.Bold))
                cat_item.addChild(child)

            self.tree_permissions.addTopLevelItem(cat_item)
            cat_item.setExpanded(True)

    def _populate_sessions_table(self, sessions: List[Dict[str, Any]]) -> None:
        self.table_sessions.setRowCount(len(sessions))
        for row, s in enumerate(sessions):
            self.table_sessions.setItem(row, 0, QTableWidgetItem(s.get("session_id", "")[:12] + "..."))
            self.table_sessions.setItem(row, 1, QTableWidgetItem(s.get("username", "")))
            self.table_sessions.setItem(row, 2, QTableWidgetItem(s.get("role_name", "")))
            self.table_sessions.setItem(row, 3, QTableWidgetItem(s.get("ip_address", "")))
            self.table_sessions.setItem(row, 4, QTableWidgetItem(s.get("user_agent", "")[:30] + "..."))
            self.table_sessions.setItem(row, 5, QTableWidgetItem(s.get("expires_at", "")[:19]))

            btn_revoke = QPushButton("Revoke")
            btn_revoke.setStyleSheet("color: #f85149;")
            btn_revoke.clicked.connect(lambda _, tok=s.get("session_id"): self._revoke_session(tok))
            self.table_sessions.setCellWidget(row, 6, btn_revoke)

    def _open_new_user_dialog(self) -> None:
        dlg = UserDialog(self, roles=self._cached_roles)
        if dlg.exec():
            data = dlg.get_data()
            success, new_u, msg = user_service.create_user(
                username=data["username"],
                password=data["password"],
                full_name=data["full_name"],
                role_id=data["role_id"],
                email=data["email"],
                operator_user_id=None
            )
            if success:
                QMessageBox.information(self, "Success", f"User account '{data['username']}' created successfully.")
                self._load_data()
            else:
                QMessageBox.warning(self, "Failed to Create User", msg)

    def _edit_user(self, user_id: str) -> None:
        user_data = next((u for u in self._cached_users if u["id"] == user_id), None)
        if not user_data:
            return

        dlg = UserDialog(self, user_data=user_data, roles=self._cached_roles)
        if dlg.exec():
            data = dlg.get_data()
            success, updated_u, msg = user_service.update_user(
                user_id=user_id,
                full_name=data["full_name"],
                email=data["email"],
                role_id=data["role_id"],
                is_active=data["is_active"],
                operator_user_id=None
            )
            # If password was provided during edit, also update password
            if success and data.get("password"):
                user_service.admin_reset_password(None, user_id, data["password"])

            if success:
                QMessageBox.information(self, "Success", "User account updated successfully.")
                self._load_data()
            else:
                QMessageBox.warning(self, "Update Failed", msg)

    def _unlock_user(self, user_id: str) -> None:
        success, msg = user_service.unlock_user(None, user_id)
        if success:
            QMessageBox.information(self, "Unlocked", msg)
            self._load_data()
        else:
            QMessageBox.warning(self, "Error", msg)

    def _admin_reset_password(self, user_id: str) -> None:
        user_data = next((u for u in self._cached_users if u["id"] == user_id), None)
        if not user_data:
            return

        pwd, ok = QInputDialog.getText(
            self, f"Reset Password for '{user_data['username']}'",
            "Enter new temporary password (min 8 chars, mixed case, digit, symbol):",
            QLineEdit.Password
        )
        if ok and pwd:
            success, msg = user_service.admin_reset_password(None, user_id, pwd)
            if success:
                QMessageBox.information(self, "Password Reset", msg)
                self._load_data()
            else:
                QMessageBox.warning(self, "Reset Failed", msg)

    def _revoke_session(self, session_id: str) -> None:
        reply = QMessageBox.question(self, "Revoke Session", "Are you sure you want to forcibly terminate this operator session?")
        if reply == QMessageBox.Yes:
            # Revoke via direct DB update
            from database.database_manager import db_manager
            from database.models.users import UserSession
            with db_manager.get_session() as session:
                sess = session.query(UserSession).filter_by(id=session_id).first()
                if sess:
                    sess.is_revoked = True
                    session.commit()
            self._load_data()
