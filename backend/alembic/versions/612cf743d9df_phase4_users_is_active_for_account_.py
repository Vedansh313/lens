"""phase4 users.is_active for account disable

Revision ID: 612cf743d9df
Revises: 2e3bb2bfc843
Create Date: 2026-07-31 02:38:25.982050

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '612cf743d9df'
down_revision: Union[str, Sequence[str], None] = '2e3bb2bfc843'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing accounts are all active: the server default backfills them, so
    # nobody is locked out by this migration running.
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    # Provenance for a disabled account — who turned it off, when, and why.
    # Nullable because they only mean anything while is_active is false.
    op.add_column('users', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('deactivated_by_user_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('deactivation_reason', sa.String(length=255), nullable=True))
    # Self-referential FK: the admin who acted is also a user. SET NULL so
    # deleting that admin does not erase the record of what they did.
    op.create_foreign_key(
        'fk_users_deactivated_by_user_id', 'users', 'users',
        ['deactivated_by_user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_users_deactivated_by_user_id', 'users', type_='foreignkey')
    op.drop_column('users', 'deactivation_reason')
    op.drop_column('users', 'deactivated_by_user_id')
    op.drop_column('users', 'deactivated_at')
    op.drop_column('users', 'is_active')
