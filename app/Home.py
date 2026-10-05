import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import text

from app.services.data_service import get_daftar_kota
from config.settings import DB_NAME
from database.connection import get_engine

st.set_page_config(
    page_title="Analisis & Forecast Harga Beras",
    layout="wide"
)

st.title("📊 Analisis & Forecast Harga Beras")
st.caption("Grafik deret waktu harga rata-rata bulanan beras medium dan premium, dari data awal sampai terbaru.")

SEMUA_KOTA = "Semua kota (rata-rata)"
LABEL_TIPE = {"medium": "Beras Medium", "premium": "Beras Premium"}


@st.cache_data(ttl=600)
def load_monthly(kode_kota: str) -> pd.DataFrame:
    """Rata-rata harga bulanan per tipe; kode_kota=SEMUA_KOTA -> rata-rata seluruh kota."""
    filter_kota = "" if kode_kota == SEMUA_KOTA else "WHERE kode_kota = :kota"
    query = text(f"""
        SELECT tipe, tahun, bulan, AVG(harga_ratarata) AS harga
        FROM history_data_beras_monthly
        {filter_kota}
        GROUP BY tipe, tahun, bulan
        ORDER BY tahun, bulan
    """)
    params = {} if kode_kota == SEMUA_KOTA else {"kota": kode_kota}
    df = pd.read_sql(query, get_engine(DB_NAME), params=params)
    df["tanggal"] = pd.to_datetime(
        dict(year=df["tahun"], month=df["bulan"], day=1)
    )
    df["Tipe"] = df["tipe"].map(LABEL_TIPE).fillna(df["tipe"])
    return df


col_kota, col_tipe = st.columns([1, 2])
kota = col_kota.selectbox("Kota", [SEMUA_KOTA] + get_daftar_kota())
tipe_dipilih = col_tipe.multiselect(
    "Jenis beras",
    options=list(LABEL_TIPE.values()),
    default=list(LABEL_TIPE.values()),
)

df = load_monthly(kota)

if df.empty:
    st.warning("Belum ada data bulanan. Jalankan agregasi bulanan terlebih dahulu.")
    st.stop()

tgl_min, tgl_max = df["tanggal"].min().date(), df["tanggal"].max().date()
if tgl_min < tgl_max:
    rentang = st.slider(
        "Rentang waktu",
        min_value=tgl_min,
        max_value=tgl_max,
        value=(tgl_min, tgl_max),
        format="MMM YYYY",
    )
else:
    rentang = (tgl_min, tgl_max)

tampil = df[
    df["Tipe"].isin(tipe_dipilih)
    & (df["tanggal"].dt.date >= rentang[0])
    & (df["tanggal"].dt.date <= rentang[1])
]

if tampil.empty or not tipe_dipilih:
    st.info("Pilih minimal satu jenis beras untuk menampilkan grafik.")
else:
    chart = (
        alt.Chart(tampil)
        .mark_line(point=True)
        .encode(
            x=alt.X("tanggal:T", title="Bulan", axis=alt.Axis(format="%b %Y")),
            y=alt.Y("harga:Q", title="Harga rata-rata (Rp/kg)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "Tipe:N",
                title="Jenis beras",
                scale=alt.Scale(domain=list(LABEL_TIPE.values()), range=["#2E86DE", "#F39C12"]),
            ),
            tooltip=[
                alt.Tooltip("tanggal:T", title="Bulan", format="%B %Y"),
                alt.Tooltip("Tipe:N", title="Jenis"),
                alt.Tooltip("harga:Q", title="Harga (Rp/kg)", format=",.0f"),
            ],
        )
        .properties(height=420)
        .interactive(bind_y=False)
    )
    st.altair_chart(chart, use_container_width=True)

    ringkas = (
        tampil.sort_values("tanggal")
        .groupby("Tipe")["harga"]
        .agg(Terbaru="last", Rata_rata="mean", Terendah="min", Tertinggi="max")
        .round(0)
    )
    ringkas.columns = ["Terbaru", "Rata-rata", "Terendah", "Tertinggi"]
    st.dataframe(ringkas.style.format("Rp {:,.0f}"), use_container_width=True)

st.info("Gunakan menu di sidebar untuk analisis harian, agregasi bulanan, forecast, dan perbandingan kota.")
