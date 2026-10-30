CLASS lhc_goods IMPLEMENTATION.
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
