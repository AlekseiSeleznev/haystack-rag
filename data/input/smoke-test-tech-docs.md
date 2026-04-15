# Smoke Test Technical Notes

## SAP SuccessFactors OData V2

Entity `EmpEmployment` commonly contains fields such as:
- `assignmentIdExternal`
- `hiringNotCompleted`
- `startDate`
- `userId`

Entity `EmpJob` often includes fields such as:
- `eventReason`
- `company`
- `businessUnit`
- `managerId`
- `jobCode`

Entity `PerPersonal` commonly includes:
- `firstName`
- `lastName`
- `gender`
- `startDate`

## 1C Notes

In 1C, metadata objects may include:
- catalogs
- documents
- information registers
- common modules

## RAG Parser Notes

For noisy technical PDFs, a fallback parser path is often necessary.
If the primary parser fails or produces weak structure, the system should still extract plain text and continue indexing.

For retrieval smoke tests, narrow structured queries usually work better than broad chatty questions.
