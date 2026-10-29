# Revue documentaire et limites de conformite

Reference : ESG Data API V4 Documentation_July_2026.pdf, version documentaire 3.0, juillet 2026.
Cette matrice porte sur les sections utilisees par le projet. Elle n'est ni une certification MSCI,
ni une affirmation que toutes les fonctions des 158 pages sont implementees.

| Sujet | Pages | Implementation / decision |
|---|---|---|
| Nouveaux droits produits V4 | 4 | Aucun catalogue n'est traite comme preuve d'acces aux valeurs |
| HTTP 429 et Retry-After | 4 | client._send, reprises bornees, header respecte |
| OAuth client_credentials et audience | 7-9 | client._authenticate, valeurs exactes du document |
| Token 24 h, reutilisation | 8 | expires_in utilise; cache memoire par processus, pas de cache disque |
| URL de base V4 | 10 | client.BASE_URL |
| POST JSON issuers recommande | 11, 17 | requests json=payload fixe Content-Type automatiquement |
| Lots issuers | 12 | data_request_id et batch_id; pas de reutilisation comme cache |
| Identifiants ISIN acceptes | 14, 17 | issuer_identifier_list depuis les ISIN d'entree |
| Facteurs et datasets | 17-18 | factor_name_list; pas de dataset_list ajoute par defaut |
| Metadonnees et facteurs retournes | 15-20 | requested_id, issuer_metadata, factors name/value |
| Permissions dans messages | 15 | messages et facteurs non resolus conserves, cause non inventee |
| Exemple demandant nom et ticker | 18-20 | references demandees explicitement; regression ajoutee |
| Donnees courantes fonds | 31-41 | fund_identifier_list avec MDSUID apres resolution |
| Lots fonds | 32 | meme mecanisme de lots que issuers |
| Coverage et lots | 42-50 | entity_type fund, product unique par appel, parcours de tous les lots |
| Coverage pendant chargement | 43 | reprise 503 espacee d'au moins 300 s, nombre borne |
| Coverage invalide apres chargement | 43 | erreur 400 explicite; pas de reprise automatique avec ancienne cle |
| References Fonds ISIN/MDSUID | 44, 48 | rapprochement exact; ambiguite signalee |
| Metadonnees facteurs | 52-54 | filtre factor_type; facteur present ne signifie pas valeur accessible |
| Catalogue produits | 57-59 | commande products, pas de deduction automatique des abonnements |
| Instrument-reference | 145-156 | non implemente; pas de remplacement silencieux CUSIP/SEDOL/statut |
| Historique | 63-144 | non implemente; aucune date historique assimilee a une date de notation |

## Ambiguites du document a ne pas masquer

Le document contient des mentions residuelles d'instruments uniquement dans certaines descriptions
alors que la table de changements p. 4 et les parametres p. 52 incluent issuer/fund.
Les exemples de code ne sont pas tous directement executables (placeholders, methodes parfois
incoherentes avec les tableaux). Le projet suit les tableaux de parametres et les structures
JSON des exemples, plutot que de recopier aveuglement ces fragments.
La description des metadonnees mentionne a la fois les permissions et le contenu du repository.
Les tests reels fournis montrent un facteur visible en metadonnees mais refuse par /issuers.
Le programme conserve cette distinction et ne diagnostique pas automatiquement une absence de licence.

## Changements de V1 vers V2

1. References demandees explicitement, meme si le mapping lit issuer_metadata.
2. Valeurs scalaires preservees, y compris 0 et False; pas d'imputation.
3. Conflits entre metadonnees et facteurs detectes au lieu d'un ecrasement silencieux.
4. Diagnostic reference_only distinct de no_data_returned et unresolved_identifier.
5. Messages, trace_id, requetes et resume conserves, y compris en cas d'echec API.
6. Commandes validate et probe pour separer entree, transport API et export.
7. Les codes exacts ITR/date/NACE/PALM ne sont plus bloques a priori: demandes seulement si
   exposes au bon niveau. Aucune substitution approximative n'a ete introduite.
8. Reprises HTTP bornees, renouvellement unique apres 401, erreurs TLS explicites.
9. Guide de migration utilisant l'environnement local deja cree par l'utilisateur.
10. Template source identique a celui de V1, sans modification des feuilles template.

## Ce qui reste a valider avec MSCI / l'equipe

- Rejet de IVA_COMPANY_RATING dans /issuers alors que /metadata/factors le decrit.
- Habilitations et couverture reelles des facteurs et produits Fonds.
- Definitions et unites de chaque candidat de mapping avant production.
- Politique de cache OAuth securise pour un usage frequent en plusieurs processus.
- Source metier de Security_Status et correspondance de FUND_SHARE_CLASS_ID.

## Tests

Les tests utilisent des reponses simulees et des structures issues des retours utilisateur.
Aucune valeur financiere simulee n'est livree comme une extraction MSCI.
Les tests couvrent les en-tetes, styles et dimensions, doublons, invalides, valeurs manquantes,
references seules, valeurs nulles/0/False, lots, OAuth, 401, 403, 429, 503 et erreurs applicatives.
