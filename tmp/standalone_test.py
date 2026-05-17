import io
import csv

def parse_money(val_str):
    if not val_str: return 0
    try:
        cleaned = val_str.replace("R$", "").strip()
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        return int(float(cleaned) * 100)
    except (ValueError, TypeError):
        return 0

def test_csv_import_logic(csv_content):
    if not csv_content.strip():
        return {"imported": 0, "errors": ["Arquivo CSV está vazio"]}

    f = io.StringIO(csv_content)
    try:
        sample = csv_content[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        f.seek(0)
        reader = csv.DictReader(f, dialect=dialect)
    except Exception as e:
        print(f"  Sniffer failed: {e}. Falling back to default.")
        f.seek(0)
        reader = csv.DictReader(f)
    
    results = []
    for row_idx, raw_row in enumerate(reader, start=2):
        row = {str(k).strip().lower(): str(v).strip() for k, v in raw_row.items() if k is not None}
        if not any(row.values()):
            continue
        
        name = row.get("nome")
        price = parse_money(row.get("preco_venda", "0"))
        cost = parse_money(row.get("custo")) if row.get("custo") else None
        
        results.append({
            "line": row_idx,
            "name": name,
            "price": price,
            "cost": cost,
            "sku": row.get("sku")
        })
    return results

# Test cases
test_data = [
    {
        "name": "Tab separated (User example)",
        "content": "nome\tsku\tdescricao\tcategoria\tpreco_venda\tcusto\tquantidade\testoque_minimo\tcodigo_barras\tncm\tcest\tcfop\tcsosn\tcst_pis\tcst_cofins\nProduto csv 1\tSKU-001\tDescrição do produto 1\tcategoria 1\t29.9\t15\t10\t2\t7.89123E+12\t3801.10.00\t01.001.00\t5102\t102\t1\t1"
    },
    {
        "name": "Semicolon separated",
        "content": "nome;sku;preco_venda;custo;quantidade\nProduto B;SKU-002;29,90;15,00;10"
    },
    {
        "name": "Mixed numbers",
        "content": "nome,preco_venda,custo\nProduto D,R$ 1.234,56,100.00"
    }
]

for case in test_data:
    print(f"Testing {case['name']}...")
    result = test_csv_import_logic(case['content'])
    for r in result:
        print(f"  Line {r['line']}: Name='{r['name']}', Price={r['price']}, Cost={r['cost']}, SKU='{r['sku']}'")
    print("-" * 20)
