/**
 * Who runs AIMIx, as the legal pages state it. None of these facts can be read from
 * the code, so none is guessed: a null value shows on the pages as a visible
 * "[à compléter : …]" marker. Fill every one in before the service opens to the public
 * (docs/legal.md lists what each is and where the law asks for it).
 */
export interface OperatorFacts {
  /** Company name (raison sociale), or the operator's full name when an individual. */
  name: string | null;
  /** E.g. "SAS au capital de 1 000 €", or "Entrepreneur individuel". */
  legalForm: string | null;
  /** Registered office, or professional address. */
  address: string | null;
  /** RCS or RNE registration with the SIREN number. */
  registration: string | null;
  /** Intra-community VAT number, when there is one. */
  vatNumber: string | null;
  /** Directeur ou directrice de la publication (a natural person). */
  publicationDirector: string | null;
  /** The address people write to: questions, data-protection requests, reports. */
  contactEmail: string | null;
  /** A telephone number (LCEN art. 1-1 asks for one, individual or company alike). */
  phone: string | null;
  /** Languages the contact point answers in (DSA art. 11 and 12), e.g. "français, anglais". */
  contactLanguages: string | null;
  /** Hosting provider: legal name, address and telephone number. */
  host: string | null;
  /** Where the servers, the database and its backups are (country or region). */
  dataLocation: string | null;
  /** Data protection officer, or a sentence saying none is designated. */
  dataProtectionOfficer: string | null;
  /** How long the hosting provider keeps server logs (IP address, requested page). */
  serverLogRetention: string | null;
  /** How long backups keep data that was deleted. */
  backupRetention: string | null;
  /** Safeguards for transfers outside the EU (adequacy decision, standard clauses). */
  transferSafeguards: string | null;
  /** Whether and what the service costs, and how it is billed. */
  pricing: string | null;
  /** The minimum age to open an account. */
  minimumAge: string | null;
  /** Consumer mediator (required when consumers are customers) and its website. */
  consumerMediator: string | null;
  /** Courts competent for disputes with professional customers. */
  competentCourt: string | null;
}

export const OPERATOR: OperatorFacts = {
  name: null,
  legalForm: null,
  address: null,
  registration: null,
  vatNumber: null,
  publicationDirector: null,
  contactEmail: null,
  phone: null,
  contactLanguages: null,
  host: null,
  dataLocation: null,
  dataProtectionOfficer: null,
  serverLogRetention: null,
  backupRetention: null,
  transferSafeguards: null,
  pricing: null,
  minimumAge: null,
  consumerMediator: null,
  competentCourt: null,
};

/** What each missing fact is called in its marker. */
export const FACT_LABELS: Record<keyof OperatorFacts, string> = {
  name: "nom ou raison sociale de l'exploitant",
  legalForm: 'forme juridique et capital social',
  address: 'adresse du siège ou adresse professionnelle',
  registration: "numéro d'immatriculation (RCS ou RNE) et SIREN",
  vatNumber: 'numéro de TVA intracommunautaire, le cas échéant',
  publicationDirector: 'nom du directeur ou de la directrice de la publication',
  contactEmail: 'adresse électronique de contact',
  phone: 'numéro de téléphone',
  contactLanguages: 'langues acceptées par le point de contact',
  host: "nom, adresse et téléphone de l'hébergeur",
  dataLocation: 'pays ou région des serveurs, de la base de données et des sauvegardes',
  dataProtectionOfficer: 'délégué à la protection des données, ou mention de son absence',
  serverLogRetention: "durée de conservation des journaux de l'hébergeur",
  backupRetention: 'durée de conservation des sauvegardes',
  transferSafeguards: 'garanties encadrant les transferts hors de l’Union européenne',
  pricing: 'prix du Service et modalités de paiement, ou gratuité',
  minimumAge: 'âge minimal pour ouvrir un compte',
  consumerMediator: 'médiateur de la consommation et son site',
  competentCourt: 'tribunaux compétents pour les clients professionnels',
};
