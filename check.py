import pandas as pd

df = pd.read_csv("btc_1h.csv")
print(df.columns.tolist())
print(df.head(3))