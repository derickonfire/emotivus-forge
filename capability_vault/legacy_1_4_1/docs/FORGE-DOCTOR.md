# Forge Doctor

Forge Doctor measures whether the current machine and extracted workspace can execute the project's registered assurance commands.

```bash
python3 Emotivus-Forge/forge.py doctor .
```

It checks:

- Required runtimes and executables
- Executables implied by absorbed commands
- Runtime version evidence
- Presence of required environment-variable **names**, never their values
- Declared sibling directories, files, and working-layout assumptions

Outputs:

- `.forge/doctor/doctor.json`
- `.forge/doctor/doctor.md`

Doctor emits a repair plan. v1.0.4 deliberately does not install software, create database users, invent credentials, alter services, or perform automatic repairs.
