# MSCI Enrichment V2

Projet Python pour enrichir des ISIN et remplir les templates Titres et Fonds.
Version du package : 0.2.0. Documentation de reference : ESG Data API V4 Documentation,
juillet 2026, version documentaire 3.0. Ne pas confondre version documentaire et endpoint V4.

## Ce que cette version garantit et ne garantit pas

- Le programme demande explicitement les noms et tickers des emetteurs.
- Il distingue references seules, valeurs ESG obtenues, absence de donnees et erreurs.
- Il conserve les en-tetes et leur ordre dans les deux feuilles template.
- Il ne remplace jamais une valeur manquante par zero.
- Il ne deduit pas les droits d'acces de la simple presence d'un facteur au catalogue.
- Il ne peut pas forcer MSCI a retourner un facteur refuse par le service.
- Les tests sont hors connexion. Aucune connexion avec vos secrets n'a ete effectuee ici.
- Les correspondances fonctionnelles restent a approuver par l'equipe metier.

## Pour Mehdi : remplacer la V1 sans recreer Python

1. Garder le dossier V1 comme sauvegarde. Decompresser V2 dans un nouveau dossier.
2. Ouvrir le nouveau dossier `msci-enrichment` dans VS Code.
3. Copier depuis V1 votre `.env` et votre fichier `data/input.xlsx` vers V2.
   Ne pas copier l'ancien dossier `src`, l'ancien mapping.json ou les anciens exports.
4. Si vous aviez modifie settings.json (produits Fonds notamment), reporter ces changements
   dans le nouveau settings.json sans remplacer aveuglement les nouveaux fichiers.
5. Garder votre environnement Python local existant. Dans le terminal PowerShell :

```powershell
$pythonProjet = "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache\Local\MSCI-Enrichment\.venv\Scripts\python.exe"
& $pythonProjet -m pip install -e ".[dev]"
& $pythonProjet -m pytest -q
& $pythonProjet -m msci_enrichment.cli validate
& $pythonProjet -m msci_enrichment.cli probe --identifier GB00BTK05J60
& $pythonProjet -m msci_enrichment.cli run
```

Le chemin ci-dessus correspond a votre environnement observe, pas a un chemin universel.
Les autres membres de l'equipe doivent utiliser leur propre environnement et leurs acces autorises.
La variable $pythonProjet ne dure que dans le terminal courant.
Le pip install -e est indispensable apres le changement de dossier : sinon Python peut encore
importer le code de V1. Les tests affichent actuellement 25 passed dans l'environnement de revision.
Si un certificat, un proxy ou une installation est bloque, contacter l'IT; ne pas contourner TLS.

## Installation pour un nouveau membre de l'equipe

Python 3.11+ et extension Python Microsoft dans VS Code. Depuis la racine du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data
```

Sur un lecteur reseau, preferer un environnement local autorise par l'IT. Ne pas copier un
venv d'un poste a l'autre. Selectionner son python.exe avec Python: Select Interpreter.
Renseigner MSCI_CLIENT_ID et MSCI_CLIENT_SECRET dans .env. Ne pas partager .env ou un token.
.env est ignore par Git mais n'est pas chiffre. Pour la production, utiliser le gestionnaire
de secrets approuve par l'entreprise. Le partage du code ne partage pas les droits MSCI.

## Entree

Fichier : `data/input.xlsx`. Feuille `Titres` et/ou `Fonds`, ligne 1 avec colonne `ISIN`.
Colonnes facultatives : `Client_ID` et `Security_Status`.
Les identifiants doivent etre du texte, pas des formules Excel.
Une feuille absente est autorisee. Les doublons et l'ordre des lignes sont conserves.
Les ISIN sont normalises (espaces externes supprimes, majuscules) et controles par cle Luhn.
Un ISIN invalide n'est pas envoye a MSCI mais sa ligne est conservee avec un diagnostic.

## Commandes disponibles

Dans les exemples, $pythonProjet designe votre python.exe.

```powershell
# Controle local du fichier d'entree et du mapping, sans appel API.
& $pythonProjet -m msci_enrichment.cli validate

# Catalogue complet: presence ne signifie pas acces aux valeurs.
& $pythonProjet -m msci_enrichment.cli metadata --entity issuer

# Un facteur precis, avec messages et trace_id.
& $pythonProjet -m msci_enrichment.cli metadata --entity issuer --factor IVA_COMPANY_RATING

# Produits du catalogue; ne pas les assimiler automatiquement a vos abonnements.
& $pythonProjet -m msci_enrichment.cli products --entity fund

# Reponse brute de l'API, sans mapping ni export, sans afficher de token.
& $pythonProjet -m msci_enrichment.cli probe --identifier GB00BTK05J60

# Choisir explicitement les facteurs du test.
& $pythonProjet -m msci_enrichment.cli probe --identifier GB00BTK05J60 --factor ISSUER_NAME --factor IVA_COMPANY_RATING

# Export complet des deux templates.
& $pythonProjet -m msci_enrichment.cli run
```

`probe --entity fund` attend un MDSUID fonds, pas un ISIN : le pipeline run resout les ISIN
via coverage, mais la commande probe est volontairement un test direct d'un endpoint.

## Sorties et interpretation

- `output/import_msci.xlsx` : uniquement Template Import Titres et Template Import Fonds.
- `output/diagnostics.json` : resume, mapping, requetes, messages, trace_id et diagnostics par ligne.

Etats par ligne :

| Etat | Sens |
|---|---|
| invalid_isin | Format ou cle ISIN invalide; aucune requete pour cet identifiant |
| unresolved_identifier | Identifiant explicitement signale comme non resolu par l'API |
| ambiguous_identifier | Plusieurs MDSUID possibles pour un ISIN fonds |
| no_data_returned | Aucune ligne de donnees retournee; ne signifie pas forcement ISIN inconnu |
| reference_only | References obtenues, mais aucune valeur ESG dans les colonnes cible |
| partial | Au moins une valeur ESG, mais des colonnes restent vides |
| complete | Toutes les colonnes cible ont une valeur, y compris les champs metier |

Un zero ou False retourne par MSCI compte comme une valeur, pas comme une absence.
Le compteur ESG exclut les references et les champs metier; il ne mesure pas la qualite des donnees.
Le programme affiche un avertissement si l'export est incomplet ou sans valeurs ESG.
Il conserve le diagnostic en cas d'erreur pendant l'enrichissement. Si une ancienne sortie existe,
elle reste inchangee apres un echec et ne doit pas etre prise pour le resultat du nouveau run.
Les erreurs de configuration avant initialisation du rapport sont affichees dans le terminal.

Les diagnostics contiennent des ISIN et des donnees de portefeuille. Ne pas les publier.
Les requetes et messages API sont conserves, jamais les en-tetes Authorization ou la reponse OAuth.

## Architecture pour l'equipe

- client.py : OAuth, HTTP, renouvellement apres 401, reprises bornees et lots.
- diagnostics.py : interpretation des reponses sans inventer la cause d'un rejet.
- pipeline.py : resolution des identifiants, demande des facteurs, mapping, orchestration.
- excel.py : lecture, controle des ISIN et ecriture dans les feuilles d'origine.
- cli.py : commandes simples pour VS Code ou un autre terminal.
- config/mapping.json : une regle par colonne cible, dans l'ordre du template.
- docs/CONFORMITE.md : lien entre les regles du projet et les pages du document.
- docs/MAPPING_REVIEW.csv : inventaire lisible des correspondances et limites.
- tests/ : tests locaux et regressions a partir des structures observees.

## Mapping : regles explicites

Le fichier mapping.json distingue les types suivants :

- factor : code exact ou candidat autorise, demande seulement s'il est au catalogue du bon niveau.
- metadata : champ de issuer_metadata; demande aussi comme facteur s'il est au catalogue.
- input : champ metier recopie de l'entree, sinon vide.
- input_isin : ISIN de la part fourni en entree.
- coverage : reference du fonds issue de coverage, ou valeur courante si retournee.
- blocked : pas de source validee, valeur vide avec explication.

Les candidats autorises sont IVA_COMPANY_RATING, INDUSTRY_ADJUSTED_SCORE, les trois poids
PILLAR_WEIGHT, IVA_RATING_TREND et FEMALE_DIRECTORS_PCT. Les unites et definitions restent a revoir.
ITR titres : code exact ITR uniquement s'il est expose. Jamais FUND_IMPLIED_TEMP_RISE.
FUND_IMPLIED_TEMP_RISE reste dans sa propre colonne Fonds du template existant; il n'est pas
utilise comme nouveau remplacement. Aucun nouvel usage de ce facteur n'a ete ajoute.
PALM_DIST et PALM_PROD : codes exacts seulement, jamais duplication du total PALM_TOTAL.
PALM_RSPO_PCT : code exact seulement, jamais remplacement par RAW_MAT_CERT_PALMOIL.
ESG_RATING_DATE : code exact seulement, jamais date d'extraction ou date historique assimilee.
NACE_GROUP_CODE : code exact seulement, jamais un indicateur SFDR de fonds.
FUND_SHARE_CLASS_ID : bloque tant que sa correspondance avec MDSUID n'est pas confirmee.
Client_ID et Security_Status : champs d'entree; le Client_ID metier n'est pas le client_id OAuth.
ISSUER_ISIN n'est pas automatiquement l'ISIN d'entree. Le diagnostic conserve les deux niveaux.
Les CUSIP/SEDOL du titre ne sont pas assimiles aux identifiants emetteur.

## Fonds

Configurer fund_products dans settings.json avec les noms exacts des produits a interroger.
Le programme appelle /coverage (entity_type fund), rapproche ISIN -> MDSUID puis appelle /funds.
Un produit visible dans le catalogue n'est pas une preuve de permission sur ses valeurs.
Le pipeline parcourt la couverture des produits configures, sans cache persistant.
Les doublons de MDSUID identiques entre produits sont fusionnes; plusieurs MDSUID distincts
pour le meme ISIN ne sont jamais departages arbitrairement.
La couverture de fonds et les droits doivent etre testes sur votre compte avant usage collectif.

## Limites techniques et recette

Le token est reutilise en memoire pendant une execution jusqu'a expiration, avec marge de securite.
Il n'est pas persiste sur disque : chaque nouvelle commande/processus peut demander un token.
Pour un usage recurrent, preferer un processus durable ou un cache securise approuve par l'IT;
ne pas lancer une commande par ISIN. Le programme ne demande pas un token par requete de donnees.
Les reprises sont bornees; Retry-After est respecte. Pour coverage HTTP 503, l'intervalle minimal
est de 300 secondes suivant la recommandation de chargement quotidien p. 43.
Les delais reseau sont des timeouts de connexion/lecture, pas une duree totale garantie.
Pas d'historique, d'instrument-reference, de conversion d'unites, de calcul derive ou d'imputation.
Une serie ou une valeur non scalaire interrompt l'export plutot que de choisir une valeur arbitraire.
Le decoupage en 50 identifiants est un choix conservateur, pas une limite universelle de /issuers.
Les operations vers un meme chemin de sortie ne doivent pas etre executees en parallele.
Les styles existants sont conserves avec openpyxl; les objets Excel avances non pris en charge
par cette bibliotheque ne font pas l'objet d'une garantie de preservation universelle.

Avant production : comparer plusieurs ISIN avec une extraction MSCI autorisee, verifier les
unites et dates, faire approuver le mapping, tester Fonds et les erreurs reseau, puis figer les
dependances dans votre environnement approuve. Les tests hors connexion ne prouvent ni vos
habilitations ni la disponibilite des valeurs en production.

## Sources

- ESG Data API V4 Documentation_July_2026.pdf, fourni par l'utilisateur.
- Mapping Factor Names.xlsx embarque dans V1, templates et Priorites de verification.
- Reponses API copiees par l'utilisateur pendant le diagnostic.
- Portail : https://developer.msci.com/apis/esg-data-api
- Bibliotheque HTTP : https://requests.readthedocs.io/

Le document MSCI n'est pas redistribue dans l'archive. Les templates fournis sont copies sans
modification. Verifier les autorisations contractuelles avant redistribution des donnees.
