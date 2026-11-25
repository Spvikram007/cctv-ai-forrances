"""
User Creation and Edit Modal Dialog (Phase 14 - Module A).
Implements input validation, password complexity verification, and role selection.
"""

from typing import Dict, Any, List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QFormLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt

from core.security.password import validate_password_strength


class UserDialog(QDialog):
    """Modal dialog for creating and editing user accounts."""

    def __init__(
        self,
        parent: Optional[QDialog] = None,
        user_data: Optional[Dict[str, Any]] = None,
        roles: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        super().__init__(parent)
        self.user_data = user_data or {}
        self.roles = roles or []
        self.is_edit = bool(self.user_data.get("id"))

        self.setWindowTitle("Edit User Account" if self.is_edit else "Create New User Account")
        self.resize(460, 380)
        self.setStyleSheet("""
            QDialog { background-color: #161b22; color: #c9d1d9; }
            QLabel { color: #c9d1d9; font-size: 10pt; }
            QLineEdit, QComboBox {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #c9d1d9;
                font-size: 10pt;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #58a6ff; }
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px 14px;
                color: #c9d1d9;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #30363d; }
            QPushButton#btnSave {
                background-color: #238636;
                border: 1px solid #2ea043;
                color: #ffffff;
            }
            QPushButton#btnSave:hover { background-color: #2ea043; }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header_title = "Update User Details" if self.is_edit else "New Surveillance User"
        lbl_head = QLabel(header_title)
        lbl_head.setStyleSheet("font-size: 13pt; font-weight: bold; color: #58a6ff; margin-bottom: 4px;")
        layout.addWidget(lbl_head)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # 1. Username
        self.txt_username = QLineEdit(self.user_data.get("username", ""))
        if self.is_edit:
            self.txt_username.setEnabled(False)
            self.txt_username.setStyleSheet("background-color: #21262d; color: #8b949e;")
        form_layout.addRow("Username:", self.txt_username)

        # 2. Full Name
        self.txt_full_name = QLineEdit(self.user_data.get("full_name", ""))
        form_layout.addRow("Full Name:", self.txt_full_name)

        # 3. Email
        self.txt_email = QLineEdit(self.user_data.get("email", "") or "")
        form_layout.addRow("Email Address:", self.txt_email)

        # 4. Role
        self.combo_role = QComboBox()
        selected_index = 0
        for idx, r in enumerate(self.roles):
            self.combo_role.addItem(r["name"], r["id"])
            if r["id"] == self.user_data.get("role_id"):
                selected_index = idx
        self.combo_role.setCurrentIndex(selected_index)
        form_layout.addRow("Assigned Role:", self.combo_role)

        # 5. Password
        pwd_label = "New Password (leave blank to keep current):" if self.is_edit else "Password:"
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        form_layout.addRow(pwd_label, self.txt_password)

        # 6. Confirm Password
        self.txt_confirm_password = QLineEdit()
        self.txt_confirm_password.setEchoMode(QLineEdit.Password)
        form_layout.addRow("Confirm Password:", self.txt_confirm_password)

        # 7. Active Status
        self.chk_active = QCheckBox("Account Active")
        self.chk_active.setChecked(self.user_data.get("is_active", True))
        form_layout.addRow("Status:", self.chk_active)

        layout.addLayout(form_layout)

        # Password help text
        lbl_help = QLabel("Minimum 8 chars: 1 uppercase, 1 lowercase, 1 digit, 1 symbol.")
        lbl_help.setStyleSheet("color: #8b949e; font-size: 8pt;")
        layout.addWidget(lbl_help)

        layout.addStretch()

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save User")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self) -> None:
        username = self.txt_username.text().strip()
        full_name = self.txt_full_name.text().strip()
        password = self.txt_password.text()
        confirm = self.txt_confirm_password.text()

        if not username:
            QMessageBox.warning(self, "Validation Error", "Username is required.")
            return
        if not full_name:
            QMessageBox.warning(self, "Validation Error", "Full name is required.")
            return

        # If creating new user, password is required
        if not self.is_edit:
            if not password:
                QMessageBox.warning(self, "Validation Error", "Password is required for new accounts.")
                return
            if password != confirm:
                QMessageBox.warning(self, "Validation Error", "Passwords do not match.")
                return
            valid, msg = validate_password_strength(password)
            if not valid:
                QMessageBox.warning(self, "Password Complexity Failed", msg)
                return
        else:
            # If editing and password was entered, validate it
            if password:
                if password != confirm:
                    QMessageBox.warning(self, "Validation Error", "Passwords do not match.")
                    return
                valid, msg = validate_password_strength(password)
                if not valid:
                    QMessageBox.warning(self, "Password Complexity Failed", msg)
                    return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        """Returns validated form values."""
        return {
            "username": self.txt_username.text().strip(),
            "full_name": self.txt_full_name.text().strip(),
            "email": self.txt_email.text().strip() or None,
            "role_id": self.combo_role.currentData(),
            "role_name": self.combo_role.currentText(),
            "password": self.txt_password.text(),
            "is_active": self.chk_active.isChecked(),
        }
