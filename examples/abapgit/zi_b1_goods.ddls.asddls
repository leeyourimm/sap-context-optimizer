@EndUserText.label: 'Synthetic goods receipt'
define root view entity ZI_B1_Goods as select from zb1_goods_table
association [0..1] to ZI_B1_Missing as _Missing on $projection.Id = _Missing.Id
{ key id as Id, quantity as Quantity }
