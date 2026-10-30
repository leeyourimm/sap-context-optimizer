CLASS lhc_goods DEFINITION INHERITING FROM cl_abap_behavior_handler.
  PRIVATE SECTION.
    METHODS complete FOR MODIFY IMPORTING keys FOR ACTION Goods~Complete.
    METHODS validateQuantity FOR VALIDATE ON SAVE IMPORTING keys FOR Goods~validateQuantity.
ENDCLASS.
CLASS lsc_goods DEFINITION INHERITING FROM cl_abap_behavior_saver.
  PROTECTED SECTION.
    METHODS save_modified REDEFINITION.
ENDCLASS.
