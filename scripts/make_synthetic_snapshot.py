"""Explicit demo/test fixture writer. Never called by read-only MCP tools."""
import argparse
from pathlib import Path


def metadata(typ, inner):
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<abapGit version="v1.0.0" serializer="LCL_OBJECT_{typ}" serializer_version="v1.0.0">\n'
            '<asx:abap xmlns:asx="http://www.sap.com/abapxml" version="1.0"><asx:values>\n'
            + inner + '\n</asx:values></asx:abap>\n</abapGit>\n')


def populate(destination):
    """All identifiers and logic below authored for this project; no company code."""
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    files = {}

    def obj(name, typ, body, ext="abap", inner=None):
        field, node = {"CLAS": ("CLSNAME", "VSEOCLASS"), "INTF": ("CLSNAME", "VSEOINTERF"),
                       "PROG": ("NAME", "PROGDIR"), "DDLS": ("DDLNAME", "DDLS"),
                       "BDEF": ("NAME", "BDEF"), "SRVD": ("NAME", "SRVD")}[typ]
        files[f"{name.lower()}.{typ.lower()}.xml"] = metadata(typ, inner or f"<{node}><{field}>{name}</{field}></{node}>")
        files[f"{name.lower()}.{typ.lower()}.{ext}"] = body

    obj("ZIF_B1_POSTING", "INTF", "INTERFACE zif_b1_posting PUBLIC.\n  METHODS post.\nENDINTERFACE.\n")
    obj("ZCL_B1_HELPER", "CLAS", """CLASS zcl_b1_helper DEFINITION PUBLIC FINAL CREATE PUBLIC.
  PUBLIC SECTION.
    INTERFACES zif_b1_posting.
    CLASS-METHODS check IMPORTING iv_quantity TYPE i RETURNING VALUE(rv_ok) TYPE abap_bool.
ENDCLASS.
CLASS zcl_b1_helper IMPLEMENTATION.
  METHOD check.
    rv_ok = xsdbool( iv_quantity > 0 ).
  ENDMETHOD.
  METHOD zif_b1_posting~post.
    " Synthetic fixture only; not a real posting API.
  ENDMETHOD.
ENDCLASS.
""")
    obj("ZBP_B1_GOODS", "CLAS", """CLASS zbp_b1_goods DEFINITION PUBLIC ABSTRACT FINAL FOR BEHAVIOR OF zi_b1_goods.
ENDCLASS.
CLASS zbp_b1_goods IMPLEMENTATION.
ENDCLASS.
""")
    files["zbp_b1_goods.clas.locals_def.abap"] = """CLASS lhc_goods DEFINITION INHERITING FROM cl_abap_behavior_handler.
  PRIVATE SECTION.
    METHODS complete FOR MODIFY IMPORTING keys FOR ACTION Goods~Complete.
    METHODS validateQuantity FOR VALIDATE ON SAVE IMPORTING keys FOR Goods~validateQuantity.
ENDCLASS.
CLASS lsc_goods DEFINITION INHERITING FROM cl_abap_behavior_saver.
  PROTECTED SECTION.
    METHODS save_modified REDEFINITION.
ENDCLASS.
"""
    files["zbp_b1_goods.clas.locals_imp.abap"] = """CLASS lhc_goods IMPLEMENTATION.
  METHOD complete.
    " 입고 완료 Complete Action: synthetic behavior, no SAP write executed.
    DATA(ok) = zcl_b1_helper=>check( iv_quantity = 1 ).
    READ ENTITIES OF zi_b1_goods IN LOCAL MODE ENTITY Goods ALL FIELDS WITH CORRESPONDING #( keys ) RESULT DATA(goods).
  ENDMETHOD.
  METHOD validateQuantity.
    DATA(ok) = zcl_b1_helper=>check( iv_quantity = 0 ).
  ENDMETHOD.
ENDCLASS.
CLASS lsc_goods IMPLEMENTATION.
  METHOD save_modified.
    " Additional Save stub: no accounting assumptions.
  ENDMETHOD.
ENDCLASS.
"""
    obj("ZI_B1_GOODS", "DDLS", """@EndUserText.label: 'Synthetic goods receipt'
define root view entity ZI_B1_Goods as select from zb1_goods_table
association [0..1] to ZI_B1_Missing as _Missing on $projection.Id = _Missing.Id
{ key id as Id, quantity as Quantity }
""", "asddls")
    obj("ZC_B1_GOODS", "DDLS", """@EndUserText.label: 'Synthetic projection'
define root view entity ZC_B1_Goods as projection on ZI_B1_Goods
{ key Id, Quantity }
""", "asddls")
    obj("ZI_B1_GOODS", "BDEF", """managed implementation in class zbp_b1_goods unique;
strict ( 2 );
define behavior for ZI_B1_Goods alias Goods
persistent table zb1_goods_table
lock master
{
  action Complete result [1] $self;
  validation validateQuantity on save { create; field Quantity; }
  determination deriveStatus on modify { create; }
}
""", "asbdef")
    obj("ZUI_B1_GOODS", "SRVD", "define service ZUI_B1_Goods {\n  expose ZC_B1_Goods as Goods;\n}\n", "srvdsrv")
    files["zui_b1_goods_o4.srvb.xml"] = metadata("SRVB", """<SRVB><METADATA><NAME>ZUI_B1_GOODS_O4</NAME></METADATA>
<CONTENT><SERVICES><item><SERVICE_CONTENT><item><SRVD_REF>
<TYPE>SRVD/SRV</TYPE><NAME>ZUI_B1_GOODS</NAME>
</SRVD_REF></item></SERVICE_CONTENT></item></SERVICES></CONTENT></SRVB>""")
    files["zb1_functions.fugr.xml"] = metadata("FUGR", """<AREAT>Synthetic B1 function group</AREAT>
<INCLUDES><SOBJ_NAME>LZB1_FUNCTIONSTOP</SOBJ_NAME></INCLUDES>
<FUNCTIONS><item><FUNCNAME>Z_B1_CHECK</FUNCNAME></item></FUNCTIONS>""")
    files["zb1_functions.fugr.z_b1_check.abap"] = "FUNCTION z_b1_check.\n  DATA(ok) = zcl_b1_helper=>check( iv_quantity = 1 ).\nENDFUNCTION.\n"
    files["zb1_functions.fugr.lzb1_functionstop.abap"] = "FUNCTION-POOL zb1_functions.\nDATA quantity TYPE i.\n"
    obj("ZB1_INCLUDE", "PROG", "DATA quantity TYPE i.\n", inner="<PROGDIR><NAME>ZB1_INCLUDE</NAME><SUBC>I</SUBC></PROGDIR>")
    obj("ZB1_PROGRAM", "PROG", "REPORT zb1_program.\nINCLUDE zb1_include.\nCALL FUNCTION 'Z_B1_CHECK'.\n")
    # Many independent methods make context reduction nontrivial and reproducible.
    methods = ["CLASS zcl_b1_large DEFINITION PUBLIC.\n  PUBLIC SECTION.\n"]
    methods += [f"    METHODS unused_{i}.\n" for i in range(120)]
    methods += ["    METHODS find_receipt.\nENDCLASS.\nCLASS zcl_b1_large IMPLEMENTATION.\n"]
    for i in range(120):
        methods += [f"  METHOD unused_{i}.\n", '    DATA(note) = \'unrelated synthetic payload ' + str(i) + ' ' + 'x' * 90 + "'.\n", "  ENDMETHOD.\n"]
    methods += ["  METHOD find_receipt.\n", "    DATA(ok) = zcl_b1_helper=>check( iv_quantity = 1 ).\n", "  ENDMETHOD.\nENDCLASS.\n"]
    obj("ZCL_B1_LARGE", "CLAS", "".join(methods))
    for name, text in files.items():
        target = path / name
        if target.exists() and target.read_text() != text:
            raise ValueError("Refusing to overwrite existing non-fixture content")
        target.write_text(text)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    populate(parser.parse_args().output)
