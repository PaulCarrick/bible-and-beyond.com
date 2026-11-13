import argparse
from pathlib import Path

from document_import import (
    DocumentProblem,
    convert,
    clean_library_html,
    html_to_text,
    save_images,
)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF to HTML and plain text."
    )
    parser.add_argument("pdf", type=Path, help="PDF file to import")
    parser.add_argument(
        "--html", type=Path, help="HTML output path (default: beside the PDF)"
    )
    parser.add_argument(
        "--text", type=Path, help="Text output path (default: beside the PDF)"
    )
    args = parser.parse_args()

    pdf_path = args.pdf.expanduser()
    if not pdf_path.is_file():
        parser.error(f"File not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        parser.error("The input file must have a .pdf extension.")

    html_path = (args.html or pdf_path.with_suffix(".html")).expanduser()
    text_path = (args.text or pdf_path.with_suffix(".txt")).expanduser()

    paths = [pdf_path.resolve(), html_path.resolve(), text_path.resolve()]
    if len(set(paths)) != 3:
        parser.error("Input, HTML output, and text output must be different files.")

    try:
        document = convert(pdf_path, pdf_path.name)
        html = clean_library_html(document.html)
        save_images(document.images)

        for output in (html_path, text_path):
            output.parent.mkdir(parents=True, exist_ok=True)

        html_path.write_text(html, encoding="utf-8")
        text_path.write_text(html_to_text(html), encoding="utf-8")
    except (DocumentProblem, OSError) as error:
        parser.exit(1, f"Error: {error}\n")

    for warning in document.warnings:
        print(f"Warning: {warning}")

    print(f"HTML: {html_path}")
    print(f"Text: {text_path}")


if __name__ == "__main__":
    main()
