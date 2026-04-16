# SAP SuccessFactors: Creating a New Employee via OData

This note captures the grounded findings from the local RAG corpus about how to create a new employee in SAP SuccessFactors via OData.

## What the documentation says

The minimum Employee Central flow is:

1. `PerPerson`
2. `EmpEmployment`
3. `EmpJob`
4. `PerPersonal`
5. Create a user through the `SCIM Users API`

The guide states that these four entities must be upserted in that order to add an employee, and that after `EmpEmployment` you can start creating the SCIM user. It also warns not to perform API edits while an HRIS sync job is running because values such as `username` may be overwritten.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.1577)`

## Minimal Employee Central flow

All four steps use the same OData upsert endpoint:

- Method: `POST`
- Endpoint: `/odata/v2/upsert`
- Content-Type: `application/json`

### Step 1: PerPerson

```json
{
  "__metadata": {
    "uri": "PerPerson"
  },
  "personIdExternal": "grantcarla"
}
```

Field description:
- `__metadata`: OData metadata wrapper for the entity being upserted.
- `__metadata.uri`: entity selector. For this minimal sample it is simply `PerPerson`.
- `personIdExternal`: external person identifier. This is the anchor ID that is reused in later entities.

What to substitute in real code:
- Replace `grantcarla` with your real external person ID.
- Exact required fields beyond this sample are tenant-specific and must be checked in the OData API Data Dictionary.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.1578)`

### Step 2: EmpEmployment

```json
{
  "__metadata": {
    "uri": "EmpEmployment(personIdExternal='grantcarla',userId='cgrant')"
  },
  "startDate": "/Date(1388534400000)/",
  "personIdExternal": "grantcarla",
  "userId": "cgrant"
}
```

Field description:
- `__metadata`: OData metadata wrapper.
- `__metadata.uri`: entity selector with the business key values embedded in the URI.
- `startDate`: employee start date in the SAP OData date wrapper format, where epoch milliseconds are embedded inside the string.
- `personIdExternal`: same external person ID used in `PerPerson`.
- `userId`: employee user ID.

Important note:
- The guide states that when you upsert `EmpEmployment`, the `User` entity is also created with the specified `userId`.
- The guide also states that creating a SCIM user is still required.

What to substitute in real code:
- Replace `grantcarla` with the real external person ID.
- Replace `cgrant` with the real user ID.
- Replace `1388534400000` with the real start date converted into the SAP OData date wrapper format.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.1579)`

### Step 3: EmpJob

```json
{
  "__metadata": {
    "uri": "EmpJob"
  },
  "jobCode": "ADMIN-1",
  "userId": "cgrant",
  "startDate": "/Date(1388534400000)/",
  "eventReason": "HIRNEW",
  "company": "ACE_USA",
  "businessUnit": "ACE_CORP",
  "managerId": "NO_MANAGER"
}
```

Field description:
- `__metadata`: OData metadata wrapper.
- `__metadata.uri`: entity selector. In this sample it is `EmpJob`.
- `jobCode`: job code.
- `userId`: employee user ID. Must match the employment/user created earlier.
- `startDate`: start date in SAP OData date wrapper format.
- `eventReason`: event reason. In the sample it is the new-hire code `HIRNEW`.
- `company`: company code.
- `businessUnit`: business unit code.
- `managerId`: manager identifier.

What to substitute in real code:
- Replace `ADMIN-1`, `HIRNEW`, `ACE_USA`, `ACE_CORP`, and `NO_MANAGER` with values valid in your tenant.
- These values are often controlled by tenant configuration and picklists.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.1580)`

### Step 4: PerPersonal

```json
{
  "__metadata": {
    "uri": "PerPersonal(personIdExternal='grantcarla',startDate=datetime'2014-01-01T00:00:00')"
  },
  "personIdExternal": "grantcarla",
  "namePrefix": "Ms",
  "gender": "F",
  "initials": "cg",
  "firstName": "Carla",
  "lastName": "Grant"
}
```

Field description:
- `__metadata`: OData metadata wrapper.
- `__metadata.uri`: entity selector with `personIdExternal` and effective-date style `startDate`.
- `personIdExternal`: same external person ID from the previous steps.
- `namePrefix`: name prefix, for example `Ms`.
- `gender`: gender code. The sample uses `F`.
- `initials`: employee initials.
- `firstName`: first name.
- `lastName`: last name.

What to substitute in real code:
- Replace all sample identity values with the actual employee data.
- Ensure the `startDate` in the URI is aligned with your intended effective date handling in the tenant.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (pp.1581-1582)`

## Onboarding-specific APIs

These are not the minimal Employee Central create-employee flow. They are used when the business process is onboarding, rehire, legal-entity transfer, or updating onboarding hiring data from an external HRIS.

### createOnboardee

Used for:
- Rehire
- Rehire on old employment
- Legal entity transfer

Sample payloads:

Rehire:

```json
{
  "userId": "400011",
  "email": "AlbusD@testCompany.com",
  "userName": "RL11",
  "password": "onb",
  "applicationId": "TAL10",
  "rehireUser": "TH123"
}
```

Rehire on old employment:

```json
{
  "userId": "INACTIVE_EMPLOYEE_USER_ID",
  "email": "EMAIL_ID",
  "password": "PASSWORD",
  "userName": "USERNAME",
  "applicationId": "APPLICATION_ID",
  "hireType": "REHIRE_OLD_EMPLOYMENT"
}
```

Legal entity transfer:

```json
{
  "userId": "400011",
  "email": "AlbusD@testCompany.com",
  "password": "onb",
  "userName": "RL11",
  "applicationId": "TAL10",
  "hireType": "LEGAL_ENTITY_TRANSFER_NEW_EMPL",
  "internalUserId": "1234"
}
```

Field description:
- `userId`: target user ID.
- `email`: email address.
- `password`: onboarding password value in the sample.
- `userName`: username/login.
- `applicationId`: application identifier.
- `rehireUser`: user ID to rehire.
- `hireType`: hire scenario selector.
- `internalUserId`: internal user ID used in the legal-entity-transfer sample.

Known validation errors from the guide:
- `MANDATORY_PARAMETERS_MISSING`
- `INVALID_EMAIL`
- `USER_ID_EXISTS`
- `USER_NAME_EXISTS`

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (pp.2438-2440)`

### updateFromExternalHrisONB

Used for updating onboarding hiring data from an external HRIS.

```json
{
  "onbStableId": "D29528C23A034FFF935246661E5F7988",
  "hireStatus": "HIRED",
  "sourceOfRecord": "ONB",
  "userName": "extHrisInfoUser"
}
```

Parameter description from the guide:
- `onbStableId`: master ID of the `ONB2Process` object. Mandatory.
- `sourceOfRecord`: source-of-record value. Mandatory. Must come from the Source of Record picklist.
- `hireStatus`: candidate hire status from the external HRIS. Mandatory. Only `HIRED` is supported.
- `assignmentIdExternal`: optional external assignment ID.
- `personIdExternal`: optional external person ID.
- `userName`: username of the new hire. Mandatory.

Important note:
- `assignmentIdExternal` and `personIdExternal` should be used only if there is no existing record in the system.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.2444)`

## What is not fully specified in the available context

- The exact SCIM user creation endpoint path is not shown in the available context.
- The exact tenant-specific required fields for `PerPerson`, `EmpEmployment`, `EmpJob`, and `PerPersonal` are not fixed by the sample payloads.
- The guide explicitly says to check the tenant-specific OData API Data Dictionary or `/odata/v2/<Entity>/$metadata`.

Sources:
- `SAP SuccessFactors API Reference Guide.pdf (p.417)`
- `SAP SuccessFactors API Reference Guide.pdf (pp.1578-1582)`

## What must be checked in the tenant before coding

1. Which additional fields are mandatory for `PerPerson`.
2. Which additional fields are mandatory for `EmpEmployment`.
3. Which additional fields are mandatory for `EmpJob`.
4. Which additional fields are mandatory for `PerPersonal`.
5. Valid values for `eventReason`, `company`, `businessUnit`, `managerId`, and other tenant-configured reference fields.
6. The real SCIM Users API endpoint and payload expected in the tenant.
7. Whether an HRIS sync job can overwrite fields such as `username`.

## Implementation-ready summary

You can already code the minimal Employee Central creation sequence using four `POST /odata/v2/upsert` calls in this order:

1. `PerPerson`
2. `EmpEmployment`
3. `EmpJob`
4. `PerPersonal`

You should carry these IDs consistently through the flow:

- `personIdExternal`
- `userId`
- start/effective dates

You should treat the following as tenant-configured values rather than hardcoded constants:

- `jobCode`
- `eventReason`
- `company`
- `businessUnit`
- `managerId`
- any additional mandatory fields discovered in the OData dictionary

If the business flow is onboarding rather than pure Employee Central creation, you should use the onboarding APIs instead:

- `createOnboardee`
- `updateFromExternalHrisONB`

But those are a separate branch from the minimal EC employee creation flow.
