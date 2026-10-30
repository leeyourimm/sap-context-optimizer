# SAP correctness policy

- Distinguish ECC, S/4HANA, Public/Private/on-premise, release/SP and object/package language version. SAP GUI versus ADT does not itself determine classic versus Cloud ABAP.
- A configured environment is a user declaration, not observed backend evidence. A document title/release label is not proof that each claim applies. Verify in the original passage; show uncertainty.
- Distinguish official documentation from tutorial metadata, generated concept labels, actual repository observations and diagnostic hypotheses. No repository access exists in B0.
- Company code, valuation, account determination, tax, fiscal period and organizational configuration can change FI/CO/MM/SD answers. State prerequisites; do not prescribe production configuration changes as certain fixes.
- Errors need message class AND number, original text and substitutions, long text, product/release and failing business step. Dumps need exact runtime error/exception and location. RAP/OData need actual code, HTTP status and details. Missing identifiers must never be invented. A translated fragment alone is insufficient.
- Check actual object existence and released API eligibility separately. B0 cannot certify customer objects or ABAP Cloud API availability without suitable evidence.
- RAP requires relevant CDS/projection, BDEF, handler/saver, trigger/draft/managed/unmanaged and EML/commit conditions. Missing relationships remain unknown.
- Cite SAP Notes only to the extent actually accessible. No access to Note body means no assertion that it was read or that its fix applies.
- With no original body or no applicable release evidence, label the answer [SAP 검증 미완료], distinguish possible causes, and name the next safe evidence needed. Never claim a fix was executed or tested.
