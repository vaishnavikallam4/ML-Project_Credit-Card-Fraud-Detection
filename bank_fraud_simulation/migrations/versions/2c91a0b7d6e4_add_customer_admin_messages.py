"""Add customer/admin communication messages.

Revision ID: 2c91a0b7d6e4
Revises: eb2d53991ac0
Create Date: 2026-10-07 18:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "2c91a0b7d6e4"
down_revision = "eb2d53991ac0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "communication_messages",
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=True),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("requested_card_action", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["cards.card_id"]),
        sa.ForeignKeyConstraint(["case_id"], ["fraud_cases.case_id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["users.user_id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_communication_messages_customer_id",
        "communication_messages",
        ["customer_id"],
    )


def downgrade():
    op.drop_index(
        "ix_communication_messages_customer_id",
        table_name="communication_messages",
    )
    op.drop_table("communication_messages")
