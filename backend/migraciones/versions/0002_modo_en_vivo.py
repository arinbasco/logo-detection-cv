"""Modo de cada análisis y fotogramas analizados de las sesiones en vivo

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # En SQLite, Alembic recrea la tabla por lotes y copia las filas que ya hay
    with op.batch_alter_table("analisis") as tabla:
        # Los análisis que ya existen son todos del modo informe
        tabla.add_column(sa.Column("modo", sa.Text(), server_default="informe", nullable=False))
        tabla.alter_column("fps", existing_type=sa.Float(), nullable=True)
        tabla.alter_column("intervalo_s", existing_type=sa.Float(), nullable=True)
        tabla.create_check_constraint(op.f("ck_analisis_modo"), "modo IN ('informe', 'en_vivo')")
    op.create_table(
        "fotograma",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analisis_id", sa.Uuid(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analisis_id"],
            ["analisis.id"],
            name=op.f("fk_fotograma_analisis_id_analisis"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fotograma")),
    )
    op.create_index("ix_fotograma_analisis_id_t_s", "fotograma", ["analisis_id", "t_s"])


def downgrade() -> None:
    op.drop_index("ix_fotograma_analisis_id_t_s", table_name="fotograma")
    op.drop_table("fotograma")
    # Las sesiones en vivo no tienen fps ni intervalo, que la versión anterior exige: se
    # borran con sus detecciones y sus recortes, que solo los referencia su detección
    op.execute(
        "DELETE FROM deteccion WHERE analisis_id IN (SELECT id FROM analisis WHERE modo = 'en_vivo')"
    )
    op.execute("DELETE FROM recorte WHERE id NOT IN (SELECT recorte_id FROM deteccion)")
    op.execute("DELETE FROM analisis WHERE modo = 'en_vivo'")
    with op.batch_alter_table("analisis") as tabla:
        tabla.drop_constraint(op.f("ck_analisis_modo"), type_="check")
        tabla.alter_column("intervalo_s", existing_type=sa.Float(), nullable=False)
        tabla.alter_column("fps", existing_type=sa.Float(), nullable=False)
        tabla.drop_column("modo")
