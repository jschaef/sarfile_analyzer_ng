#!/usr/bin/python3
from PyPDF4 import PdfFileMerger
from os import remove, path

def create_multi_pdf(pdf_field: list, outfile: str):
    rm_field = pdf_field.copy()
    merger = PdfFileMerger(strict=False)
    while len(pdf_field) > 0:
        input = open(pdf_field.pop(0), "rb")
        merger.append(input)
    output = open(outfile, 'wb')
    merger.write(output)
    output.close()
    for file in rm_field:
        if path.exists(file):
            remove(file)
    return outfile
