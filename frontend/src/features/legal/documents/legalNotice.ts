import type { LegalDocument } from './types';

/** Mentions légales: who publishes and who hosts the site (LCEN). */
export const LEGAL_NOTICE: LegalDocument = {
  title: 'Mentions légales',
  updated: '31 octobre 2026',
  markdown: `
## Éditeur

Le site et le service AIMIx (le « Service ») sont édités par :

- {{name}}
- {{legalForm}}
- Adresse : {{address}}
- Immatriculation : {{registration}}
- TVA intracommunautaire : {{vatNumber}}
- Contact : {{contactEmail}}
- Téléphone : {{phone}}

Directeur ou directrice de la publication : {{publicationDirector}}.

## Hébergement

Le Service est hébergé par : {{host}}.

Les serveurs, la base de données et leurs sauvegardes sont situés : {{dataLocation}}.

## Point de contact

{{contactEmail}} est le point de contact unique du Service, pour ses utilisateurs comme pour les
autorités des États membres, la Commission européenne et le comité européen des services
numériques (règlement (UE) 2022/2065 sur les services numériques, art. 11 et 12). Langues
acceptées : {{contactLanguages}}.

## Signaler un contenu illicite

Pour signaler un contenu que vous estimez illicite, écrivez à {{contactEmail}} en indiquant :
l'emplacement précis du contenu, les raisons pour lesquelles il vous paraît illicite, vos nom et
adresse électronique, et une déclaration confirmant que les informations fournies sont exactes et
faites de bonne foi. Chaque signalement reçoit un accusé de réception et une décision motivée.

## Propriété intellectuelle

Les éléments du site (nom, logo, textes, interfaces) appartiennent à l'éditeur ou font l'objet
d'une licence. Les contenus que vous créez avec le Service restent les vôtres, dans les
conditions des [conditions générales d'utilisation](/terms).

## Données personnelles et cookies

Le traitement de vos données et les traceurs utilisés sont décrits dans la
[politique de confidentialité](/privacy).
`,
};
