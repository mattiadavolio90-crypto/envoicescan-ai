// Specchio lato client della policy applicata dal server in
// services/auth_service.py :: valida_password_compliance().
//
// La verità resta il server — questo serve solo a dire i requisiti PRIMA che
// l'utente prema invio. Finora i due form dicevano "almeno 8 caratteri" mentre
// il server ne chiede 10 più le categorie: l'utente scopriva i requisiti veri
// uno alla volta, perché il worker restituisce solo il primo errore.
//
// Deliberatamente NON replichiamo blacklist e pattern (password comuni,
// sequenze, carattere ripetuto): sono liste lunghe che divergerebbero in
// silenzio. Quelle restano al server, e il suo messaggio arriva a video.

export const PASSWORD_MIN_LEN = 10;
export const PASSWORD_MIN_CATEGORIE = 3;

export const PASSWORD_HINT = "Almeno 10 caratteri, con maiuscole, minuscole, numeri o simboli";

// Le stesse 4 categorie del server, di cui ne servono almeno 3.
function categoriePresenti(password: string): number {
  const checks = [
    /[A-Z]/, // maiuscola
    /[a-z]/, // minuscola
    /[0-9]/, // numero
    /[!@#$%^&*()\-_=+[\]{}|;:,.<>?/~`'"\\]/, // simbolo
  ];
  return checks.filter((re) => re.test(password)).length;
}

// Ritorna il primo requisito non soddisfatto, o null se la password passa i
// controlli che sappiamo replicare fedelmente. null NON significa "accettata":
// il server ha l'ultima parola e può ancora rifiutarla.
export function erroreLocalePassword(password: string): string | null {
  // [...password] conta i CODEPOINT come len() di Python: password.length conta
  // unita' UTF-16, quindi un emoji varrebbe 2 e il client direbbe "ok" su una
  // password che il server rifiuta per lunghezza ("Ab1!" + 3 emoji: 10 in JS,
  // 7 in Python). Errore nella direzione scomoda: promettere e poi rifiutare.
  if ([...password].length < PASSWORD_MIN_LEN) {
    return `La password deve essere di almeno ${PASSWORD_MIN_LEN} caratteri`;
  }
  if (categoriePresenti(password) < PASSWORD_MIN_CATEGORIE) {
    return "Usa almeno 3 tra: maiuscole, minuscole, numeri e simboli";
  }
  return null;
}
