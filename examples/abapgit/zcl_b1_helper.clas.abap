CLASS zcl_b1_helper DEFINITION PUBLIC FINAL CREATE PUBLIC.
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
