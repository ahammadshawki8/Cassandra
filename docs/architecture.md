# Architecture

## The whole system

```mermaid
flowchart TD
    XL["workbook.xlsx<br/><i>someone edited a model</i>"]
    GCS["Cloud Storage<br/><code>OBJECT_FINALIZE</code>"]
    PS["Pub/Sub<br/><i>at least once delivery</i>"]
    CR["Cloud Run<br/><i>scales to zero</i>"]
    FS[("Firestore<br/>runs · attempts · verdicts<br/>dismissals · delivery claims")]

    XL -->|dropped in| GCS
    GCS -->|fires| PS
    PS -->|push| CR
    CR <-->|"claim(messageId)<br/>persist"| FS

    CR --> CARTO

    subgraph DET ["Deterministic · no model calls"]
        CARTO["<b>Cartographer</b><br/>parse · dependency DAG<br/>region clustering · R1C1 signatures"]
        BLAST["<b>Blast radius</b><br/>how far a change reaches,<br/>weighted toward output figures"]
        HUNT["<b>Five detectors</b><br/>hardcode · range · pattern<br/>sign · reference"]
        CARTO --> BLAST --> HUNT
    end

    subgraph AG ["Agent fleet · Gemini 3.5 Flash · zero tools"]
        SEM["<b>Semantic Auditor</b><br/>does the formula compute<br/>what its label claims?"]
        ADJ["<b>Adjudicator</b><br/>real defect, or a<br/>legitimate modelling choice?"]
        PATCH["<b>Patcher</b><br/>writes the smallest<br/>correct edit"]
        SEM --> ADJ --> PATCH
    end

    HUNT --> SEM

    PATCH -->|proposed fix| VER{"<b>Verifier</b><br/>recalculate the workbook"}

    VER -->|"moved as predicted,<br/>nothing else touched"| OK["<b>Proven</b><br/>shown with its diff"]
    VER -->|"wrong, or it broke<br/>something else"| REJ["<b>Rejected</b>"]
    REJ -->|"back with the reason<br/>it failed"| PATCH
    REJ -.->|"after 3 attempts"| QUAR["<b>Quarantined</b><br/>raised for a human"]

    OK --> UI["Dashboard<br/><i>only proven results reach the user</i>"]
    QUAR --> UI

    classDef gcp fill:#E8F0FE,stroke:#8AB4F8,stroke-width:2px,color:#1A237E
    classDef det fill:#F5F3FF,stroke:#B4A7F5,stroke-width:1.5px,color:#33304A
    classDef agent fill:#F2EFFB,stroke:#7B6CF6,stroke-width:2px,color:#33304A
    classDef oracle fill:#E4F8F1,stroke:#4FC3A1,stroke-width:3px,color:#23795F
    classDef good fill:#E4F8F1,stroke:#4FC3A1,stroke-width:2px,color:#23795F
    classDef bad fill:#FFF6E0,stroke:#FFC145,stroke-width:2px,color:#96660A
    classDef plain fill:#FFFFFF,stroke:#EDE7F8,stroke-width:2px,color:#33304A

    class GCS,PS,CR,FS gcp
    class CARTO,BLAST,HUNT det
    class SEM,ADJ,PATCH agent
    class VER oracle
    class OK good
    class REJ,QUAR bad
    class XL,UI plain
```

## The verification loop

The whole system exists to make this loop trustworthy. Nothing reaches the user that has not been through it.

```mermaid
sequenceDiagram
    autonumber
    participant D as Detectors
    participant A as Adjudicator
    participant P as Patcher
    participant V as Verifier
    participant W as Workbook copy

    D->>A: candidate defect, with evidence
    A-->>D: legitimate modelling choice, dismissed
    A->>P: confirmed, critical

    loop up to 3 attempts
        P->>V: proposed formula + predicted value
        V->>W: apply to a copy, never the original
        W-->>V: every cell, recalculated
        alt target moved exactly as predicted, nothing else did
            V-->>P: proven
        else wrong value, empties the cell, or collateral movement
            V-->>P: rejected, and why
        end
    end

    Note over V,P: after three failures the finding is<br/>quarantined for a human, never guessed at
```

## Where the model is trusted, and where it is not

```mermaid
flowchart LR
    subgraph NEVER ["Never asks the model"]
        direction TB
        N1["parsing the workbook"]
        N2["building the dependency graph"]
        N3["clustering regions"]
        N4["locating candidates"]
        N5["<b>verifying every repair</b>"]
        N6["deciding what happens next"]
    end

    subgraph ASKS ["Asks the model"]
        direction TB
        Y1["does this formula compute<br/>what its label claims?"]
        Y2["is this a defect, or a<br/>legitimate modelling choice?"]
        Y3["what is the correct repair?"]
    end

    ASKS -->|"every answer is checked<br/>by recalculation"| NEVER

    classDef never fill:#E4F8F1,stroke:#4FC3A1,stroke-width:2px,color:#23795F
    classDef asks fill:#F2EFFB,stroke:#7B6CF6,stroke-width:2px,color:#33304A
    class N1,N2,N3,N4,N5,N6 never
    class Y1,Y2,Y3 asks
```

Three questions go to Gemini. Each is one a parser genuinely cannot answer. Everything else, including the verification that decides whether the model was right, is plain code.

The agents hold **no tools at all**. Not one can read a file, mutate a workbook, or reach the network. Each receives evidence that deterministic code assembled and returns a typed judgement. A prompt injected into a cell label can at worst produce a wrong judgement, which the Verifier then rejects by recalculating, because the Verifier asks the model nothing.
