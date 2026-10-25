# Broadcast Copilot

**[Try the live demo](https://broadcast-copilot-aakash-56875895.westus2.cloudapp.azure.com)**

Broadcast Copilot helps football broadcasters turn match statistics into clear, timely on-screen graphics. Built for the Microsoft Premier League hackathon, it uses a simulated match, synthetic player and historical data.

## Who it is for

Broadcast producers, commentators and graphics teams who want useful player and team insights during a match. Producers can review drafts, edit the wording, choose a graphic style and approve what viewers see.

## How it works

1. The backend counts incoming match events and automatically suggests moments such as pressure surges, increased shots, player involvement and substitute contributions.
2. It retrieves comparable historical statistics using indexed SQL queries and calculates the comparisons in code.
3. When a producer selects **Generate draft**, AI proposes wording and a supported graphic style. The app validates the response and supplies the verified numbers for the graphic.
4. The producer edits and approves the draft before it appears in the audience preview. Saved drafts, published graphics and decision history persist in SQLite.

The app uses **React and TypeScript** for the interface, **Python and FastAPI** for the backend, and **Docker** for deployment. Match events, historical records and pitch movement in this demo are synthetic.

## Microsoft tools used

- **Microsoft Foundry / Azure OpenAI:** hosts the GPT-4.1 mini deployment used to draft insights and suggest graphic styles.
- **Azure Virtual Machines:** hosts the application and its persistent storage, with HTTPS access for the public demo.
