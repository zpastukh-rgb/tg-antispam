export type ModerationSeverity = "low" | "medium" | "high";

export type ModerationLexeme = {
  category:
    | "religion"
    | "esoteric"
    | "magic"
    | "divination"
    | "occult"
    | "mystic_practices"
    | "sects"
    | "spiritual_practices";
  keyword: string;
  aliases: string[];
  translit: string[];
  regexSafe: string;
  severity: ModerationSeverity;
};

export const HOMOGLYPH_MAP: Record<string, string> = {
  a: "а",
  c: "с",
  e: "е",
  o: "о",
  p: "р",
  x: "х",
  y: "у",
  k: "к",
  m: "м",
  t: "т",
  h: "н",
  b: "в",
  "@": "а",
  "0": "о",
  "1": "и",
  "3": "з",
  "4": "а",
  "5": "с",
  "6": "б",
  "7": "т",
  "8": "в",
  "9": "д",
};

export const OBFUSCATION_SEPARATOR_RE = /[\u200b\u200c\u200d\u2060\s._\-/*|,:;]+/g;

export function normalizeForKeywordScan(input: string): string {
  const source = (input || "").toLowerCase().replace(/ё/g, "е");
  const mapped = Array.from(source)
    .map((ch) => HOMOGLYPH_MAP[ch] || ch)
    .join("");
  return mapped.replace(OBFUSCATION_SEPARATOR_RE, " ").trim();
}

export function normalizeCompact(input: string): string {
  return normalizeForKeywordScan(input).replace(/\s+/g, "");
}

export const RELIGION_ESOTERIC_LEXEMES: ModerationLexeme[] = [
  { category: "religion", keyword: "религ", aliases: ["религия", "религиозный"], translit: ["relig", "religiya"], regexSafe: "р[еe]л[иi1][гg][иi1]", severity: "medium" },
  { category: "religion", keyword: "православ", aliases: ["православие"], translit: ["pravoslav"], regexSafe: "пр[аa]восл[аa]в", severity: "medium" },
  { category: "religion", keyword: "христиан", aliases: ["христианство"], translit: ["christian"], regexSafe: "[хx][рr]исти[аa]н", severity: "medium" },
  { category: "religion", keyword: "ислам", aliases: ["мусульман", "коран"], translit: ["islam", "muslim", "quran"], regexSafe: "[иiu][сs][лl][аa]м", severity: "medium" },
  { category: "religion", keyword: "иудаизм", aliases: ["тора", "талмуд"], translit: ["judaism", "torah"], regexSafe: "[иi]уд[аa]и[зz]м", severity: "medium" },
  { category: "religion", keyword: "будд", aliases: ["буддизм"], translit: ["buddh"], regexSafe: "будд", severity: "medium" },
  { category: "religion", keyword: "индуизм", aliases: ["кришна"], translit: ["hindu", "krishna"], regexSafe: "[иi]нду[иi]зм", severity: "medium" },
  { category: "religion", keyword: "миссионер", aliases: ["проповедь"], translit: ["missionary", "preach"], regexSafe: "м[иi]сс[иi]он[еe]р", severity: "high" },
  { category: "religion", keyword: "обращение в веру", aliases: ["принять веру"], translit: ["convert to faith"], regexSafe: "обр[аa]щ[еe]н[иi][еe]\\s+в\\s+в[еe]ру", severity: "high" },

  { category: "esoteric", keyword: "эзотер", aliases: ["эзотерика"], translit: ["esoteric"], regexSafe: "[эe]зот[еe]р", severity: "medium" },
  { category: "magic", keyword: "магия", aliases: ["магич"], translit: ["magiya", "magic"], regexSafe: "м[аa][гg][иi1]", severity: "high" },
  { category: "magic", keyword: "ведьм", aliases: ["ведьма", "ведьмовство"], translit: ["witch"], regexSafe: "в[еe]дьм", severity: "high" },
  { category: "magic", keyword: "колдов", aliases: ["колдун"], translit: ["sorcery"], regexSafe: "колдов", severity: "high" },
  { category: "magic", keyword: "приворот", aliases: ["приворожу"], translit: ["privorot", "love spell"], regexSafe: "пр[иi]в[оo0]р[оo0]т", severity: "high" },
  { category: "magic", keyword: "отворот", aliases: ["остуда"], translit: ["otvorot"], regexSafe: "[оo]тв[оo0]р[оo0]т", severity: "high" },
  { category: "magic", keyword: "порч", aliases: ["порча"], translit: ["porcha", "curse"], regexSafe: "п[оo0]рч", severity: "high" },
  { category: "magic", keyword: "сглаз", aliases: ["сглазили"], translit: ["evil eye"], regexSafe: "сгл[аa]з", severity: "high" },
  { category: "magic", keyword: "денежный ритуал", aliases: ["ритуал на деньги"], translit: ["money ritual"], regexSafe: "д[еe]н[еe]жн\\w*\\s+риту[аa]л", severity: "high" },

  { category: "divination", keyword: "гадани", aliases: ["гадание", "гадалка"], translit: ["fortune telling"], regexSafe: "г[аa]д[аa]н[иi]", severity: "high" },
  { category: "divination", keyword: "таро", aliases: ["карты таро", "расклад"], translit: ["tarot", "taro"], regexSafe: "т[аa@]р[оo0]", severity: "high" },
  { category: "divination", keyword: "рун", aliases: ["руны"], translit: ["runes"], regexSafe: "р[уu]н", severity: "high" },
  { category: "divination", keyword: "астролог", aliases: ["астрология"], translit: ["astrology"], regexSafe: "[аa]стролог", severity: "high" },
  { category: "divination", keyword: "гороскоп", aliases: ["натальная карта"], translit: ["horoscope", "natal chart"], regexSafe: "г[оo0]р[оo0]ск[оo0]п", severity: "medium" },
  { category: "divination", keyword: "нумеролог", aliases: ["нумерология", "матрица судьбы"], translit: ["numerology", "destiny matrix"], regexSafe: "нум[еe]ролог", severity: "high" },
  { category: "divination", keyword: "родовая программа", aliases: ["родовые программы", "чистка рода"], translit: ["ancestral program"], regexSafe: "родов\\w*\\s+программ", severity: "high" },

  { category: "occult", keyword: "оккульт", aliases: ["оккультизм"], translit: ["occult"], regexSafe: "[оo]кк[уu]льт", severity: "high" },
  { category: "occult", keyword: "сатанизм", aliases: ["сатанист"], translit: ["satanism"], regexSafe: "с[аa]т[аa]н[иi]зм", severity: "high" },
  { category: "occult", keyword: "люцифер", aliases: ["люциферианство"], translit: ["lucifer"], regexSafe: "л[юu]ц[иi]ф[еe]р", severity: "high" },
  { category: "occult", keyword: "демонолог", aliases: ["демонология"], translit: ["demonology"], regexSafe: "д[еe]монолог", severity: "high" },
  { category: "occult", keyword: "пентаграм", aliases: ["пентаграмма", "пентакль"], translit: ["pentagram", "pentacle"], regexSafe: "п[еe]нт[аa]гр[аa]м", severity: "high" },

  { category: "mystic_practices", keyword: "чакр", aliases: ["чакры", "чакральный"], translit: ["chakra"], regexSafe: "ч[аa]к\\W*р", severity: "high" },
  { category: "mystic_practices", keyword: "аур", aliases: ["аура"], translit: ["aura"], regexSafe: "[аa][уu]р", severity: "medium" },
  { category: "mystic_practices", keyword: "энергопрактик", aliases: ["энергетическая практика"], translit: ["energy practice"], regexSafe: "[еe]н[еe]рг\\w*пр[аa]кт", severity: "high" },
  { category: "mystic_practices", keyword: "вибрац", aliases: ["вибрации"], translit: ["vibration"], regexSafe: "в[иi]бр[аa]ц", severity: "medium" },
  { category: "mystic_practices", keyword: "квантов практик", aliases: ["квантовое исцеление"], translit: ["quantum practice", "quantum healing"], regexSafe: "кв[аa]нтов\\w*\\s+пр[аa]кт", severity: "high" },
  { category: "mystic_practices", keyword: "регресс", aliases: ["регрессия в прошлые жизни"], translit: ["regression", "past life regression"], regexSafe: "р[еe]гр[еe]сс", severity: "high" },
  { category: "mystic_practices", keyword: "карм", aliases: ["карма", "кармический"], translit: ["karma"], regexSafe: "к[аa]рм", severity: "medium" },
  { category: "mystic_practices", keyword: "спиритизм", aliases: ["медиум"], translit: ["spiritism", "medium"], regexSafe: "сп[иi]р[иi]т[иi]зм", severity: "high" },
  { category: "mystic_practices", keyword: "шаманизм", aliases: ["шаман"], translit: ["shamanism", "shaman"], regexSafe: "ш[аa]м[аa]н[иi]зм", severity: "high" },

  { category: "sects", keyword: "секта", aliases: ["сектант"], translit: ["secta", "cult"], regexSafe: "с[еe]кт[аa]", severity: "high" },
  { category: "sects", keyword: "культ", aliases: ["тайный культ"], translit: ["cult"], regexSafe: "к[уu]льт", severity: "high" },
  { category: "sects", keyword: "деструктивный культ", aliases: ["тоталитарная секта"], translit: ["destructive cult"], regexSafe: "д[еe]стр[уu]кт[иi]вн\\w*\\s+к[уu]льт", severity: "high" },

  { category: "spiritual_practices", keyword: "медитац", aliases: ["медитация"], translit: ["meditation"], regexSafe: "м[еe]д[иi]т[аa]ц", severity: "low" },
  { category: "spiritual_practices", keyword: "ретрит", aliases: ["духовный ретрит"], translit: ["retreat"], regexSafe: "р[еe]тр[иi]т", severity: "medium" },
  { category: "spiritual_practices", keyword: "инициац", aliases: ["инициация"], translit: ["initiation"], regexSafe: "[иi]н[иi]ц[иi][аa]ц", severity: "medium" }
];

export const HIGH_SEVERITY_REGEX_PATTERNS: RegExp[] = RELIGION_ESOTERIC_LEXEMES
  .filter((x) => x.severity === "high")
  .map((x) => new RegExp(`(?:^|\\b|_)${x.regexSafe}(?:\\b|$|_)`, "iu"));

export const OBFUSCATION_GUARD_PATTERNS: RegExp[] = [
  /т[\W_]*[аa@][\W_]*р[\W_]*[оo0]/iu,
  /м[\W_]*[аa][\W_]*[гg][\W_]*[иi1][\W_]*[яya]/iu,
  /п[\W_]*р[\W_]*[иi1][\W_]*в[\W_]*[оo0][\W_]*р[\W_]*[оo0][\W_]*т/iu,
  /ч[\W_]*а[\W_]*к[\W_]*р[\W_]*[ыiy]/iu,
  /р[\W_]*[еe][\W_]*л[\W_]*[иi1][\W_]*[гg][\W_]*[иi1][\W_]*[яya]/iu
];

export const FUZZY_MATCHING_SUGGESTIONS = {
  distanceByLength: [
    { maxLen: 5, distance: 1 },
    { maxLen: 9, distance: 2 },
    { maxLen: 32, distance: 3 }
  ],
  applyOnlyForSeverity: ["high"],
  applyOnlyIfNoExactHit: true,
  preconditions: ["normalized", "compact-normalized", "tokenized"]
};
