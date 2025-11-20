import pandas as pd

def generate_insights(df_results, out_path="logs/insights.txt"):
    if df_results.empty:
        return

    best = df_results.sort_values("total_return_pct", ascending=False).head(10)

    lines = []
    lines.append("=== BEST RESULTS ===\n")

    for _, row in best.iterrows():
        lines.append(
            f"{row['strategy']} | {row['asset']} | {row['interval']} | risk={row['risk']} | return={row['total_return_pct']:.2f}%"
        )

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
