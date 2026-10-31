import type { LegalDocument } from './types';

/**
 * Politique de confidentialité (RGPD art. 13). Every technical statement here is what
 * the code does; keep it true when the code changes (docs/legal.md, "Keeping the pages
 * true"). The settings it quotes are their defaults: change the text with them.
 */
export const PRIVACY_POLICY: LegalDocument = {
  title: 'Politique de confidentialité',
  updated: '31 octobre 2026',
  markdown: `
Cette politique explique quelles données personnelles le Service AIMIx traite, pourquoi, avec
qui elles sont partagées, combien de temps elles sont conservées et comment exercer vos droits.

## Responsable du traitement

{{name}}, {{address}}. Contact pour toute question ou demande : {{contactEmail}}.

Délégué à la protection des données : {{dataProtectionOfficer}}.

## Les données traitées

**Votre compte.** Votre nom d'utilisateur, la date de création du compte et le fournisseur de
modèles choisi. Votre mot de passe n'est jamais conservé en clair : seule une empreinte
(PBKDF2-SHA256) l'est. Aucune adresse électronique ni aucun nom n'est demandé.

**Votre session.** Un jeton d'accès gardé en mémoire dans l'onglet, et un jeton de
renouvellement dans un cookie (voir « Cookies et stockage local »). Le serveur ne garde qu'une
empreinte du jeton de renouvellement.

**Vos clés d'API.** Les clés OpenRouter, TogetherAI ou Meta que vous enregistrez sont chiffrées
sur le serveur et ne vous sont jamais renvoyées ; seuls leurs quatre derniers caractères sont
affichés.

**Vos contenus.** Ce que vous créez et faites dans le Service : vos pipelines (noms, rôles,
consignes, modèles), vos exécutions (entrées, documents joints, résultats de chaque étape,
appels d'outils et vos réponses aux demandes d'approbation, avec leurs arguments), vos
planifications, vos intégrations (adresse du serveur MCP ; les valeurs d'en-têtes sont
chiffrées), vos fichiers (téléversés ou produits par vos agents) et votre consommation (jetons,
coûts). Ces contenus peuvent contenir des données sur d'autres personnes : vous en êtes
responsable (voir les [conditions générales d'utilisation](/terms)).

**Le chat.** Les messages du chat ne sont pas enregistrés sur le serveur ; un pipeline que le
chat lance à votre demande est enregistré comme toute exécution. La conversation d'une mission
est gardée dans votre navigateur, pour l'onglet ouvert seulement.

**Votre voix.** Si vous dictez une demande avec le micro de Missions, votre navigateur vous
demande d'abord l'accès au micro. L'enregistrement est envoyé au Service, qui le transmet pour
transcription et ne le conserve pas ; seul le texte transcrit revient dans la zone de saisie, où
vous le relisez avant de l'envoyer.

**La sécurité.** Pour limiter les tentatives de connexion et les abus, le Service compte les
requêtes par adresse IP, par nom d'utilisateur et par compte. Il n'enregistre ni l'adresse IP ni
le nom d'utilisateur à cette fin, seulement une empreinte calculée avec une clé secrète du serveur
(une donnée pseudonymisée), le temps de la fenêtre
de comptage (d'une minute à une heure) ; une fois la fenêtre écoulée, elle est supprimée au fil
des requêtes suivantes. Les journaux techniques de l'application contiennent
des identifiants et des résultats, jamais vos contenus. Le serveur journalise, pour chaque
requête, l'adresse IP, la date, la page demandée et la réponse ; ces journaux sont conservés par
l'hébergeur.

## Finalités et bases légales

| Finalité | Base légale |
|---|---|
| Fournir le Service : compte, pipelines, exécutions, fichiers, planifications | Exécution du contrat (RGPD, art. 6.1.b) |
| Sécuriser le Service : limitation des tentatives, prévention des abus, journaux | Intérêt légitime à protéger le Service et ses utilisateurs (art. 6.1.f) |
| Répondre à vos demandes et respecter nos obligations légales | Obligation légale (art. 6.1.c) |

Le Service ne fait ni publicité, ni mesure d'audience, ni profilage, et ne prend aucune décision
automatisée produisant des effets juridiques à votre égard. Vos contenus ne servent pas à
entraîner des modèles d'IA de l'éditeur.

## Destinataires

Vos données ne sont ni vendues ni louées. Elles sont accessibles aux seules personnes habilitées
de l'éditeur, et transmises aux prestataires suivants, dans la limite de ce qui est nécessaire.

**Hébergeur.** {{host}} héberge le Service, sa base de données et vos fichiers.

**Services utilisés à votre demande.** Lorsque vous exécutez un pipeline, discutez dans le chat,
planifiez une équipe ou dictez une demande :

- *Le fournisseur de modèles que vous choisissez* (OpenRouter, TogetherAI ou Meta) reçoit les
  consignes, entrées, documents et résultats intermédiaires nécessaires à chaque appel de
  modèle. Avec votre propre clé, il les traite dans le cadre de votre compte chez lui et de ses
  conditions, qui peuvent prévoir la conservation ou l'utilisation de ces données : consultez
  ses réglages de confidentialité.
- *La transcription vocale* (Meta, avec votre clé Meta), lorsque vous dictez une demande, reçoit
  l'enregistrement de votre voix et le traite dans le cadre de votre compte chez Meta et de ses
  conditions.
- *Le service de recherche web* (Tavily), lorsque vos agents utilisent la recherche web, reçoit
  leurs requêtes de recherche, qu'il peut transmettre à des moteurs de recherche tiers.
- *Le bac à sable d'exécution de code* (E2B), lorsque vos agents exécutent du Python, reçoit le
  code et les fichiers d'entrée choisis ; le bac à sable n'a pas accès à internet et est détruit
  après chaque appel.
- *Vos serveurs MCP* reçoivent les arguments des appels d'outils que vos agents leur adressent.
- *Les sites web* qu'un agent consulte reçoivent une requête du serveur du Service.

## Transferts hors de l'Union européenne

Certains de ces prestataires sont établis hors de l'Union européenne, notamment aux États-Unis.
Ces transferts sont encadrés par : {{transferSafeguards}}.

## Durées de conservation

- **Compte et contenus** : tant que le compte existe. Vous pouvez supprimer à tout moment une
  exécution, un pipeline, un fichier ou votre compte entier ; la suppression du compte efface
  immédiatement ses données et ses fichiers.
- **Sauvegardes** : {{backupRetention}}.
- **Empreintes servant à limiter les tentatives** : la durée de la fenêtre de comptage (une heure
  au plus), puis suppression au fil des requêtes suivantes.
- **Journaux de l'hébergeur** : {{serverLogRetention}}.
- **Conversation d'une mission dans le navigateur** : jusqu'à la fermeture de l'onglet ou la
  déconnexion.

## Vos droits

Vous disposez des droits d'accès, de rectification, d'effacement, de limitation, de portabilité
et d'opposition, ainsi que du droit de définir des directives sur le sort de vos données après
votre décès.

Depuis la page **Settings → Account**, vous pouvez à tout moment télécharger une copie des
données de votre compte (fichier JSON, qui liste aussi vos fichiers ; chacun se télécharge depuis
la page **Files**), changer votre mot de passe et supprimer votre compte. Pour toute autre
demande, notamment si vous ne pouvez plus vous connecter ou si votre compte est trop volumineux
pour être copié depuis le Service, écrivez à {{contactEmail}} : nous répondons dans un délai d'un
mois, et pouvons vous demander de quoi vérifier que le compte est le vôtre.

Vous pouvez aussi introduire une réclamation auprès de la CNIL ([www.cnil.fr](https://www.cnil.fr)).

## Cookies et stockage local

Le Service n'utilise que des traceurs strictement nécessaires au service que vous demandez ; ils
sont donc exemptés de consentement, et aucun bandeau n'est affiché.

| Nom | Type | Finalité | Durée |
|---|---|---|---|
| \`aimix_refresh\` | Cookie HttpOnly, Secure, SameSite=Strict, envoyé à \`/api/token\` seulement | Garder votre session ouverte | 1 jour |
| \`aimix.mission.v1.*\` | Stockage de session du navigateur | Garder la conversation d'une mission dans l'onglet | Fermeture de l'onglet ou déconnexion |

Aucune mesure d'audience, aucune publicité, aucun contenu tiers : les polices sont servies par le
Service lui-même, et la politique de sécurité du site interdit le chargement de ressources
externes.

## Sécurité

Mots de passe conservés sous forme d'empreinte, clés et en-têtes chiffrés, connexions en HTTPS,
cloisonnement des données par compte, limitation des tentatives de connexion, approbation
préalable des actions des outils MCP (activée par défaut), exécution du code dans un bac à sable
isolé.

## Contenus générés par l'IA

Les réponses du chat et les résultats des agents sont produits par des modèles d'intelligence
artificielle : ils sont signalés comme tels dans le Service, et les documents PDF et Word que vos
agents enregistrent l'indiquent dans leurs métadonnées.

## Mineurs

Le Service est réservé aux personnes ayant au moins {{minimumAge}}.

## Modifications

Cette politique peut évoluer avec le Service ; la date de mise à jour figure en haut de la page.
`,
};
