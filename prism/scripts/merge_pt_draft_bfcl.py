#!/usr/bin/env python3
"""Merge PT MT-drafts into bfcl_extracted.json's turns. Same safety
property as merge_pt_draft_gsm8k.py: writes to turns_pt_draft (a NEW
field), never overwrites turns_pt (which stays a list of None and is
what pt_available() actually checks) — a draft cannot get run against
L=1 by accident, only an explicit promotion after native post-edit can.
"""
import json
from pathlib import Path

TRANSLATIONS = {
"bfcl_multi_turn_base_1": [
    "Sou o alex. Verifica se o diretório atual está sob o meu nome e lista todo o conteúdo visível e oculto no diretório atual, por favor.",
    "Vai à pasta workspace e move um dos ficheiros 'log.txt' para uma nova pasta 'archive'.",
    "Investiga dentro de 'log.txt' a ocorrência da palavra 'Error'.",
    "Por fim, mostra as últimas 20 linhas do ficheiro.",
],
"bfcl_multi_turn_base_3": [
    "Como parte do meu projeto de fotografia mais recente, preciso de reunir ficheiros que tenham 'test' no nome, em qualquer pasta dentro do diretório atual. Podes ajudar-me a localizá-los?",
    "Depois de os identificar, o próximo passo é garantir que as imagens e os ficheiros de texto são copiados em segurança para uma pasta 'backup_tests' dentro do mesmo diretório. Isso pode ser feito?",
],
"bfcl_multi_turn_base_6": [
    "Está a ficar tarde por aqui, e estou a terminar as minhas notas do dia. Por favor, inicia a criação de um ficheiro na nossa pasta partilhada, chamando-o 'Annual_Report_2023.docx'.",
    "Olá, quero colocar algumas estatísticas no relatório anual. Aqui estão as coisas que quero colocar: 'Company Earning: 2000 Company Expenditure: 500 Company Name: Gorilla'.",
    "Posso ver o que está dentro de 'Annual_Report_2023.docx'?",
    "Vamos analisar 'Annual_Report_2023.docx'. Quantas palavras contém?",
    "Para concluir, guarda o número de palavras num novo ficheiro report_word_count.txt na pasta partilhada existente.",
],
"bfcl_multi_turn_base_9": [
    "Lembro-me que devia ter um documento chamado 'FinalReport.txt' na pasta 'Documentation'.",
    "Faz uma cópia de 'FinalReport.txt' para a pasta 'Archives' dentro da pasta 'Documentation', garantindo que o duplicado é guardado como 'ArchivedFinalReport2024.txt'.",
    "Organiza e ordena metodicamente a primeira linha de 'ArchivedFinalReport2024.txt' por ordem alfabética, para verificar a clareza e a sequência.",
],
"bfcl_multi_turn_base_10": [
    "Olá, podes criar uma nova pasta chamada 'Projects' dentro da pasta workspace?",
    "Vamos mover o documento de proposta do projeto para esta pasta 'Projects', mas vamos renomeá-lo para 'final_proposal_2024'.",
    "Dentro desta pasta, começa um novo ficheiro, chama-lhe 'notes.md', para capturar todos os destaques das nossas reuniões.",
    "Além disso, cria um ficheiro chamado 'summary.txt' e escreve 'Hello' nele. Depois, faz uma comparação rápida entre este e o 'notes.md' para encontrar diferenças na informação.",
    "Por fim, conta o número de carateres em 'summary.txt'.",
],
"bfcl_multi_turn_base_12": [
    "Vai à pasta 'Documents' e cria um novo ficheiro chamado 'summary.txt', podes fazer isso? Se já existir, devolve um erro.",
    "Em 'Documents', vamos registar um tema profundo 'quantum computing' e escrevê-lo em 'summary.txt'. O ficheiro deve conter apenas 'quantum computing' no seu conteúdo.",
    "Seria ótimo perceber quão extenso este ficheiro se tornou. Importas-te de contar as palavras em 'summary.txt' para mim?",
],
"bfcl_multi_turn_base_16": [
    "Na pasta research, há um ficheiro chamado 'research_notes.txt'. Por favor, faz uma cópia de segurança prioritária movendo uma cópia dele para a pasta chamada 'archives' dentro de research, chamando o novo ficheiro '2024_research_backup.txt'.",
    "Agora, pega no conteúdo de '2024_research_backup.txt' que acabámos de criar e ordena as linhas alfabeticamente.",
    "Depois de a lista estar ordenada, descobre quantas linhas tem o ficheiro '2024_research_backup.txt' já ordenado.",
],
"bfcl_multi_turn_base_25": [
    "Verifica no diretório atual se existe um ficheiro chamado 'summary.txt'. Se existir, o que tem dentro?",
    "Copia-o para 'Research2023'.",
    "Depois da revisão, organiza as linhas em 'summary.txt' alfabeticamente.",
    "Conclui calculando o total de linhas em 'summary.txt' já ordenado, para confirmar que está tudo meticulosamente organizado.",
],
"bfcl_multi_turn_base_26": [
    "Podias, por favor, ir ao diretório temporário e listar todos os ficheiros disponíveis aí mesmo no terminal? Gostava de os percorrer rapidamente, incluindo os ficheiros ocultos.",
    "O que está dentro do último ficheiro apresentado?",
    "Cria um ficheiro docx com o mesmo nome do ficheiro anterior mas mudando o formato; devem também ter o mesmo conteúdo.",
],
"bfcl_multi_turn_base_29": [
    "Abre a pasta 'VisionX'. Qual é a utilização de disco, em formato legível, dessa pasta?",
    "Cria um ficheiro com um nome baseado no número de bytes usados. Deve estar no formato 'number.pdf'.",
    "Por fim, nesse ficheiro, escreve a minha última pergunta.",
],
"bfcl_multi_turn_base_37": [
    "Podias ir à pasta temp e, para cada ficheiro aí dentro, contar o número de linhas?",
    "Agora, percorre o misterioso 'dev_summary.txt' e procura quaisquer menções ou vestígios de 'server error'.",
    "Cria um novo ficheiro cujo nome seja o número de linhas mas em formato txt, e acrescenta-lhe a segunda frase que contenha 'server error'.",
],
"bfcl_multi_turn_base_38": [
    "Perdi um documento importante que incluía investigação extensa. Ajuda-me a localizar um ficheiro chamado 'findings_report' dentro de 'SuperResearch'. Podes removê-lo, a ele e à pasta.",
    "O que resta no diretório atual, incluindo os ficheiros ocultos?",
],
"bfcl_multi_turn_base_39": [
    "Preciso que cries uma nova pasta chamada 'WebDevProjects' onde quer que estejas a trabalhar atualmente.",
    "Entra na pasta e preenche a pasta 'WebDevProjects' com 3 ficheiros: 'styles.css', 'index.html', e 'script.js' com o conteúdo 'Hello World!', 'Hi World!', 'Halo World!' em cada um.",
    "Qual é o nome do segundo ficheiro por ordem do sistema? Não listes os ficheiros ocultos.",
    "Podes mostrar o conteúdo do primeiro ficheiro por ordem do sistema?",
],
}

def main():
    path = Path("prism/suite/w2_staging/bfcl_extracted.json")
    suite = json.loads(path.read_text())
    missing = [t["id"] for t in suite["tasks"] if t["id"] not in TRANSLATIONS]
    assert not missing, f"missing translations for: {missing}"
    for t in suite["tasks"]:
        want = TRANSLATIONS[t["id"]]
        assert len(want) == len(t["turns_en"]), (
            f"{t['id']}: {len(want)} translated turns vs "
            f"{len(t['turns_en'])} english turns")
        t["turns_pt_draft"] = want  # DRAFT field, see module docstring
    Path("prism/suite/w2_staging/bfcl_pt_draft.json").write_text(
        json.dumps(suite, ensure_ascii=False, indent=1))
    print(f"draft PT written for {len(TRANSLATIONS)}/{len(suite['tasks'])} "
          f"BFCL tasks ({sum(len(v) for v in TRANSLATIONS.values())} turns) "
          f"-> bfcl_pt_draft.json (turns_pt still [None,...] in the real "
          f"suite file — drafts cannot run by accident)")

if __name__ == "__main__":
    main()
