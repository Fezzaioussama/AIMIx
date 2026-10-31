import type { LegalDocument } from './types';

/**
 * Conditions générales d'utilisation. The bracketed passages are choices the operator
 * makes with a lawyer (pricing, consumers, mediation); docs/legal.md lists them.
 */
export const TERMS: LegalDocument = {
  title: "Conditions générales d'utilisation",
  updated: '31 octobre 2026',
  markdown: `
## 1. Objet

Les présentes conditions régissent l'utilisation du service AIMIx (le « Service »), édité par
{{name}} (l'« Éditeur », voir les [mentions légales](/legal)). En créant un compte, vous les
acceptez.

## 2. Le Service

AIMIx permet de concevoir et d'exécuter des équipes d'agents d'intelligence artificielle
(« pipelines ») : chaque agent a un rôle, un modèle et des outils (recherche web, lecture de pages,
calcul, fichiers, exécution de code Python dans un bac à sable, serveurs MCP que vous connectez).

Le Service est en version bêta : il évolue, et peut être interrompu pour maintenance ou en cas
d'incident, sans garantie de disponibilité.

## 3. Compte

Vous créez un compte avec un nom d'utilisateur et un mot de passe, que vous gardez confidentiel.
Vous êtes responsable de l'activité de votre compte. Le Service est réservé aux personnes ayant
au moins {{minimumAge}}.

## 4. Prix

{{pricing}}

Les appels de modèles sont facturés par le fournisseur de modèles dont vous enregistrez la clé
(OpenRouter, TogetherAI ou Meta), selon ses tarifs et dans le cadre de votre compte chez lui. Vous
pouvez fixer des plafonds de dépense par exécution.

## 5. Services tiers

Vos agents utilisent des services tiers : le fournisseur de modèles choisi, et selon leurs
outils, un service de recherche web, un bac à sable d'exécution de code, les sites consultés et
vos serveurs MCP. Leurs conditions s'appliquent à ce que vous leur confiez ; la
[politique de confidentialité](/privacy) les décrit.

## 6. Vos contenus

Vous restez titulaire des contenus que vous apportez et de ceux que vos agents produisent pour
vous. Vous accordez à l'Éditeur le droit, limité à ce qui est nécessaire pour fournir le Service,
de les héberger, de les traiter et de les transmettre aux services tiers que vous utilisez.

Vous garantissez disposer des droits nécessaires sur vos contenus et, lorsqu'ils contiennent des
données personnelles d'autres personnes, d'une base légale pour les traiter et de leur avoir
fourni l'information requise. Lorsque vous utilisez le Service pour le compte d'une organisation
qui traite des données personnelles, l'Éditeur agit en tant que sous-traitant au sens du RGPD ;
un accord de traitement des données est disponible sur demande à {{contactEmail}}.

## 7. Usages interdits

Il est interdit d'utiliser le Service pour :

- publier, stocker ou traiter des contenus illicites, ou porter atteinte aux droits de tiers ;
- attaquer, sonder ou perturber le Service, ses utilisateurs ou des tiers, ou contourner ses
  limites et quotas ;
- mettre en œuvre une pratique d'intelligence artificielle interdite par le règlement européen
  sur l'IA (manipulation, exploitation de vulnérabilités, notation sociale, etc.) ;
- prendre, sans intervention humaine, des décisions ayant des effets importants sur des
  personnes, notamment en matière d'emploi, d'éducation, de crédit ou d'accès à des services
  essentiels ;
- diffuser des contenus générés par l'IA qui imitent des personnes réelles ou informent le
  public sur des sujets d'intérêt général sans indiquer qu'ils ont été générés par l'IA.

## 8. Résultats générés par l'IA

Les réponses et résultats des agents sont produits par des modèles d'IA. Ils peuvent être
inexacts, incomplets ou biaisés, et ne constituent pas un conseil professionnel. Vérifiez-les
avant de vous y fier, et vérifiez chaque action qu'un outil vous demande d'approuver. Le Service
les signale comme générés par l'IA ; ne retirez pas ce signalement lorsque la loi l'exige.

## 9. Signalement de contenus illicites et modération

Tout contenu illicite peut être signalé à {{contactEmail}}, selon les modalités des
[mentions légales](/legal). L'Éditeur ne surveille pas les contenus privés de ses utilisateurs
et n'utilise aucun outil de modération automatisée : il examine chaque signalement, et peut
alors retirer un contenu ou suspendre un compte (article 10). Vous pouvez contester une telle
décision en écrivant à la même adresse.

## 10. Export, suspension et suppression

Vous pouvez à tout moment télécharger les données de votre compte dans un format structuré
(JSON) et vos fichiers, pour les conserver ou les reprendre dans un autre service (la copie d'un
compte très volumineux est fournie sur demande à {{contactEmail}}), et supprimer votre compte
depuis **Settings → Account** ; ses données sont alors effacées. L'Éditeur peut suspendre ou fermer un compte qui enfreint ces conditions,
après vous en avoir informé et indiqué les motifs, sauf urgence.

## 11. Responsabilité

L'Éditeur fournit le Service avec diligence. Sa responsabilité ne saurait être engagée pour les
contenus que vous créez, les résultats générés par l'IA que vous utilisez sans les vérifier, ou
les services tiers que vous choisissez. Rien dans ces conditions ne limite les droits que la loi
reconnaît aux consommateurs.

## 12. Données personnelles

Leur traitement est décrit dans la [politique de confidentialité](/privacy).

## 13. Modification des conditions

L'Éditeur peut modifier ces conditions ; les changements importants vous sont annoncés dans le
Service avant leur entrée en vigueur. Si vous les refusez, vous pouvez supprimer votre compte.

## 14. Droit applicable et litiges

Ces conditions sont soumises au droit français. Si vous êtes consommateur, vous pouvez recourir
gratuitement au médiateur de la consommation : {{consumerMediator}} ; vous pouvez aussi saisir la
juridiction de votre domicile. Si vous êtes un professionnel, les litiges relèvent des
{{competentCourt}}.

## 15. Contact

{{contactEmail}}
`,
};
