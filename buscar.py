from whoosh.index import open_dir
from whoosh.qparser import MultifieldParser, OrGroup
from whoosh.query import Term, And
import os

CAMINHO_INDICE = "indice_funcionarios"
print("Pasta atual:", os.getcwd())
print("Índice:", os.path.abspath(CAMINHO_INDICE))
ix = open_dir(CAMINHO_INDICE)
with ix.searcher() as s:
    print("Whoosh abriu com", s.doc_count(), "documentos")


def buscar(termo=None, vinculo=None, diretoria=None, area=None, cargo=None):
    with ix.searcher() as searcher:
        queries = []

        if termo:
            # Busca em múltiplos campos (nome, cargo, local, etc.)
            parser = MultifieldParser(["nome_completo", "cargo_exercicio", "cpf", "rg", "cargo_efetivo", "local", "area"],
                                      schema=ix.schema, group=OrGroup)
            queries.append(parser.parse(termo))

        if vinculo:
            queries.append(Term("vinculo", vinculo))
        if diretoria:
            queries.append(Term("diretoria", diretoria))
        if area:
            queries.append(Term("area", area))
        if cargo:
            queries.append(Term("cargo_exercicio", cargo))

        if not queries:
            print("Nenhum critério informado.")
            return

        query_final = And(queries) if len(queries) > 1 else queries[0]
        results = searcher.search(query_final, limit=30)

        print(f"🔍 Resultados encontrados: {len(results)}")
        for r in results:
            print(f"\n--- {r['nome_completo']} ---")
            print(f"Vínculo: {r['vinculo']}")
            if r['vinculo'] == 'SERVIDOR':
                print(f"Matrícula: {r['matricula']}")
                print(f"Cargo efetivo: {r['cargo_efetivo']}")
                print(f"Cargo em exercício: {r['cargo_exercicio']}")
                print(f"Diretoria: {r['diretoria']}")
            else:
                print(f"Empresa: {r['empresa']}")
                print(f"Cargo: {r['cargo_exercicio']}")
                print(f"Subtipo: {r['subtipo_vinculo']}")
            print(f"Local: {r['local']}")
            print(f"Área: {r['area']}")


# Exemplo de uso interativo
if __name__ == "__main__":
    while True:
        print("\n" + "=" * 50)
        termo = input("Termo de busca (ou Enter para ignorar): ").strip()
        vinculo = input("Filtrar por vínculo (servidor/terceirizado): ").strip().upper()
        diretoria = input("Filtrar por diretoria (ex: CGR.09): ").strip()
        area = input("Filtrar por área: ").strip()
        cargo = input("Filtrar por cargo exato: ").strip()

        if not termo and not vinculo and not diretoria and not area and not cargo:
            print("Saindo...")
            break

        buscar(termo if termo else None,
               vinculo if vinculo else None,
               diretoria if diretoria else None,
               area if area else None,
               cargo if cargo else None)
