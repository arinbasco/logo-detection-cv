"""Tablas iniciales: analisis, recorte y deteccion

Revision ID: 0001
Revises:
Create Date: 2026-11-04 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analisis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nombre_video", sa.String(length=255), nullable=False),
        sa.Column("estado", sa.Text(), nullable=False),
        sa.Column("progreso", sa.Float(), nullable=False),
        sa.Column("duracion_s", sa.Float(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("intervalo_s", sa.Float(), nullable=False),
        sa.Column("umbral", sa.Float(), nullable=False),
        sa.Column("fotogramas_analizados", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminado", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('en_cola', 'procesando', 'completado', 'fallido')",
            name=op.f("ck_analisis_estado"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analisis")),
    )
    op.create_table(
        "recorte",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recorte")),
    )
    op.create_table(
        "deteccion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analisis_id", sa.Uuid(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.Column("marca", sa.Text(), nullable=False),
        sa.Column("confianza", sa.Float(), nullable=False),
        sa.Column("x1", sa.Integer(), nullable=False),
        sa.Column("y1", sa.Integer(), nullable=False),
        sa.Column("x2", sa.Integer(), nullable=False),
        sa.Column("y2", sa.Integer(), nullable=False),
        sa.Column("recorte_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analisis_id"],
            ["analisis.id"],
            name=op.f("fk_deteccion_analisis_id_analisis"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorte_id"], ["recorte.id"], name=op.f("fk_deteccion_recorte_id_recorte")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deteccion")),
    )
    op.create_index("ix_deteccion_analisis_id_t_s", "deteccion", ["analisis_id", "t_s"])
    op.create_index("ix_deteccion_recorte_id", "deteccion", ["recorte_id"])


def downgrade() -> None:
    op.drop_index("ix_deteccion_recorte_id", table_name="deteccion")
    op.drop_index("ix_deteccion_analisis_id_t_s", table_name="deteccion")
    op.drop_table("deteccion")
    op.drop_table("recorte")
    op.drop_table("analisis")
