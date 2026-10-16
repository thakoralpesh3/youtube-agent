"""
Autonomous Indian & Gujarati Festival Detector.
Maintains a rich festival calendar (2026-2027) with special emphasis on
automobile worship days (Vishwakarma Puja, Dussehra/Vahan Puja, Dhanteras),
plus dynamic Gemini AI fallback for detecting any tithi-based or regional celebrations.
"""

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import config
from growth.model_resolver import get_candidate_models

logger = logging.getLogger("festival_detector")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HISTORY_FILE = config.OUTPUT_DIR / "festival_history.json"


class FestivalInfo(BaseModel):
    is_festival: bool = True
    festival_name: str
    date_str: str  # YYYY-MM-DD
    significance: str
    motorcycle_theme: str
    greeting_headline: str
    blessing_message_hi: str
    blessing_message_gu: str
    blessing_message_en: str


# Pre-computed curated festival calendar for 2026-2027 (including dates in IST)
CURATED_FESTIVALS: Dict[str, Dict[str, str]] = {
    # 2026
    "2026-01-14": {
        "name": "Makar Sankranti / Uttarayan",
        "significance": "Festival of Sun transit, kites, joy, and open-road celebration",
        "theme": "Open road touring on Royal Enfield, sky full of kites, festive riding freedom",
        "headline": "Happy Makar Sankranti & Uttarayan!",
        "hi": "मकर संक्रांति और उत्तरायण की हार्दिक शुभकामनाएं! आपकी हर रॉयल एनफील्ड राइड पतंग की तरह नई ऊंचाइयों को छुए।",
        "gu": "મકર સંક્રાંતિ અને ઉત્તરાયણની હાર્દિક શુભકામનાઓ! તમારી રોયલ એન્ફિલ્ડ સવારી આકાશની જેમ અડીખમ અને તેજસ્વી રહે.",
        "en": "Wishing all Royal Enfield riders a high-flying and blessed Makar Sankranti & Uttarayan!",
    },
    "2026-01-26": {
        "name": "Republic Day",
        "significance": "National Pride, Constitution, and Brotherhood",
        "theme": "Tri-Color Royal Enfield rallies, patriotic pride, made like a gun",
        "headline": "Happy 77th Republic Day!",
        "hi": "गणतंत्र दिवस की हार्दिक शुभकामनाएं! भारत की शान, रॉयल एनफील्ड की पहचान। जय हिन्द!",
        "gu": "પ્રજાસત્તાક દિવસની હાર્દિક શુભકામનાઓ! મા ભોમની રક્ષા અને દેશનું ગૌરવ. જય હિન્દ!",
        "en": "Proudly celebrating the spirit of the nation with the timeless roar of Royal Enfield!",
    },
    "2026-02-15": {
        "name": "Maha Shivratri",
        "significance": "Day of Lord Shiva, strength, resilience, and unshakeable power",
        "theme": "Riding with the fierce resilience and calmness of Mahadev on your Royal Enfield",
        "headline": "Har Har Mahadev - Shubh Maha Shivratri!",
        "hi": "महाशिवरात्रि की मंगलमय शुभकामनाएं! देवाधिदेव महादेव की कृपा से आपकी हर यात्रा सुरक्षित और शक्तिशाली हो।",
        "gu": "મહાશિવરાત્રિની હાર્દિક શુભકામનાઓ! હર હર મહાદેવના આશીર્વાદથી તમારી યાત્રા સદાય મંગલમય રહે.",
        "en": "May Lord Shiva bless every mile of your journey with strength and fearlessness!",
    },
    "2026-03-03": {
        "name": "Holi (Holika Dahan)",
        "significance": "Victory of good over evil, bonfire of positivity",
        "theme": "Burning away obstacles, blessings for pure riding discipline",
        "headline": "Happy Holi & Holika Dahan!",
        "hi": "होलिका दहन और होली की शुभकामनाएं! बुराई पर अच्छाई की विजय, आपके जीवन में ऊर्जा और उमंग भरे।",
        "gu": "હોળી અને હોલિકા દહનની હાર્દિક શુભેચ્છાઓ! તમામ નકારાત્મકતા બળીને ભસ્મ થાય અને જીવન તેજસ્વી બને.",
        "en": "May the divine fire of Holi illuminate your roads with strength and prosperity!",
    },
    "2026-03-04": {
        "name": "Dhuleti (Festival of Colors)",
        "significance": "Vibrant colors, camaraderie, and joy",
        "theme": "Colorful roads, vibrant rides, and pure Royal Enfield brotherhood",
        "headline": "Happy Dhuleti - Festival of Colors!",
        "hi": "धुलेंडी की रंगबिरंगी शुभकामनाएं! आपकी रॉयल एनफील्ड के साथ हर सफर खुशियों के रंगों से सराबोर रहे।",
        "gu": "ધૂળેટી પર્વની હાર્દિક શુભેચ્છાઓ! રંગોના આ પાવન પર્વે તમારી દરેક સવારી રોમાંચક અને સુરક્ષિત રહે.",
        "en": "Add vibrant miles to your journey! Wishing everyone a colorful and thrilling Dhuleti!",
    },
    "2026-08-15": {
        "name": "Independence Day",
        "significance": "79 Years of Indian Freedom, Courage, and Unity",
        "theme": "Tricolor flags on Royal Enfield handle bars, salute to soldiers and pure freedom of the open road",
        "headline": "Happy Independence Day - Vande Mataram!",
        "hi": "स्वतंत्रता दिवस की हार्दिक शुभकामनाएं! तिरंगे की शान, रॉयल एनफील्ड की दहाड़। वन्दे मातरम्!",
        "gu": "સ્વાતંત્ર્ય દિવસની હાર્દિક શુભેચ્છાઓ! દેશની આઝાદી અને રોયલ રાઇડિંગનું અનોખું સ્વાભિમાન. વંદે માતરમ્!",
        "en": "Saluting the courage of our nation. Ride free, ride proud on your Royal Enfield!",
    },
    "2026-08-28": {
        "name": "Raksha Bandhan",
        "significance": "Sacred bond of protection and unconditional love",
        "theme": "Riding home to protect and celebrate with family; safety first on every ride",
        "headline": "Happy Raksha Bandhan!",
        "hi": "रक्षाबंधन की हार्दिक शुभकामनाएं! हर बहन की दुआ और रॉयल एनफील्ड की सुरक्षित राइड सदा आपके साथ रहे।",
        "gu": "રક્ષાબંધનની હાર્દિક શુભકામનાઓ! સુરક્ષિત સવારી અને પવિત્ર પ્રેમનો અતૂટ સંબંધ સદાય જળવાય રહે.",
        "en": "A promise of protection on every road. Wishing you a warm and safe Raksha Bandhan!",
    },
    "2026-09-04": {
        "name": "Krishna Janmashtami",
        "significance": "Birth of Lord Krishna, courage, divine righteousness, and celebration",
        "theme": "Divine joy, cruising into celebrations with pure devotion and thunderous thump",
        "headline": "Shubh Krishna Janmashtami!",
        "hi": "श्री कृष्ण जन्माष्टमी की हार्दिक शुभकामनाएं! भगवान श्री कृष्ण की कृपा से आपकी हर मंजिल सुगम हो। जय श्री कृष्णा!",
        "gu": "શ્રી કૃષ્ણ જન્માષ્ટમીની હાર્દિક શુભકામનાઓ! નંદ ઘેર આનંદ ભયો, જય કન્હૈયા લાલ કી!",
        "en": "May Lord Krishna steer your life and rides towards boundless happiness and success!",
    },
    "2026-09-05": {
        "name": "Nandotsav & Teachers' Day",
        "significance": "Celebration of Nandotsav (Dahi Handi) and reverence for masters & mentors",
        "theme": "Honoring the master mechanics and mentors of life; divine festive celebrations with Royal Enfield pride",
        "headline": "Shubh Nandotsav & Happy Teachers' Day!",
        "hi": "नंदोत्सव एवं शिक्षक दिवस की हार्दिक शुभकामनाएं! गुरुजनों और कारीगरों के हुनर को नमन, जिनके आशीर्वाद से हर सफर सफल होता है।",
        "gu": "નંદોત્સવ અને શિક્ષક દિવસની હાર્દિક શુભકામનાઓ! જીવનના સાચા ગુરુઓ અને મા ચામુંડાના આશીર્વાદ તમારી સાથે રહે.",
        "en": "Saluting the mentors who guide our journey, and celebrating the joyous spirit of Nandotsav with Royal Enfield power!",
    },
    "2026-09-14": {
        "name": "Ganesh Chaturthi",
        "significance": "Arrival of Lord Ganesha - Vighnaharta (Remover of Obstacles) and patron of new ventures",
        "theme": "Welcoming Bappa, praying for obstacle-free rides, blessing your motorcycle before every journey",
        "headline": "Ganpati Bappa Morya - Happy Ganesh Chaturthi!",
        "hi": "गणेश चतुर्थी की हार्दिक शुभकामनाएं! विघ्नहर्ता बाप्पा आपके हर सफर की रुकावटें दूर करें और आपकी रॉयल एनफील्ड हमेशा गरजती रहे।",
        "gu": "ગણેશ ચતુર્થીની હાર્દિક શુભકામનાઓ! ગણપતિ બાપ્પા મોરિયાના આશીર્વાદથી તમારો દરેક પ્રવાસ સુખમય અને નિર્વિઘ્ન રહે.",
        "en": "May Lord Ganesha remove every obstacle from your path and bless your Royal Enfield journeys!",
    },
    "2026-09-17": {
        "name": "Vishwakarma Puja & Jayanti",
        "significance": "Worship of Lord Vishwakarma - Divine Architect, Engineer, and God of Machines and Tools",
        "theme": "The ultimate festival for automobile workshops! Washing, garlanding, and tuning Royal Enfield engines and thanking the machines",
        "headline": "Shubh Vishwakarma Jayanti - Worship of Machines!",
        "hi": "विश्वकर्मा पूजा की हार्दिक शुभकामनाएं! मशीनों और औजारों के देव भगवान विश्वकर्मा आपके वाहन और कारीगरी को शक्ति प्रदान करें।",
        "gu": "વિશ્વકર્મા જયંતિની હાર્દિક શુભેચ્છાઓ! મશીન, ટેક્નોલોજી અને રોયલ એન્ફિલ્ડ એન્જિનના દેવ ભગવાન વિશ્વકર્મા સદાય સહાય રહે.",
        "en": "Dedicated to the machines we revere. Wishing all engineers, mechanics, and Royal Enfield riders a blessed Vishwakarma Puja!",
    },
    "2026-10-11": {
        "name": "Navratri Begins (Ghatasthapana)",
        "significance": "9 Days of Divine Shakti, Garba, devotion, and Maa Durga / Maa Chamunda worship",
        "theme": "Invoking Maa Chamunda's divine protection on every Royal Enfield rider and vehicle",
        "headline": "Jai Mata Di - Shubh Navratri!",
        "hi": "शारदीय नवरात्रि की पावन शुभकामनाएं! मां चामुंडा की कृपा से आपका जीवन और आपकी हर यात्रा शक्ति और सुरक्षा से परिपूर्ण हो।",
        "gu": "શુભ નવરાત્રિ! મા ચામુંડાના આશીર્વાદ તમારા પરિવાર અને તમારી રોયલ એન્ફિલ્ડ રાઇડ પર સદાય વરસતા રહે. જય માતાજી!",
        "en": "May Maa Chamunda grant you strength, fearless confidence, and supreme protection on every highway!",
    },
    "2026-10-20": {
        "name": "Dussehra & Vijayadashami (Vahan Puja)",
        "significance": "Victory of Truth, Shastra Puja (Weapons) and Vahan Puja (Vehicle Blessing)",
        "theme": "Traditional Vahan Puja for Royal Enfield motorcycles with marigold flowers, lemon, and vermilion swastik",
        "headline": "Shubh Vijayadashami & Auspicious Vahan Puja!",
        "hi": "विजयादशमी एवं वाहन पूजा की हार्दिक शुभकामनाएं! आपकी रॉयल एनफील्ड हमेशा विजय और गर्व का प्रतीक बने।",
        "gu": "દશેરા અને વાહન પૂજનની હાર્દિક શુભેચ્છાઓ! અસત્ય પર સત્યનો વિજય અને તમારી રોયલ એન્ફિલ્ડની અજેય સવારી.",
        "en": "Happy Dussehra & Blessed Vahan Puja! Celebrate the timeless triumph of courage with Royal Enfield!",
    },
    "2026-11-06": {
        "name": "Dhanteras (Dhantrayodashi)",
        "significance": "Day of Wealth, Health (Lord Dhanvantari), and Auspicious Vehicle Buying & Upgrades",
        "theme": "Upgrading genuine Royal Enfield parts, servicing, and celebrating prosperity on two wheels",
        "headline": "Shubh Dhanteras - Prosperity & Power!",
        "hi": "धनतेरस की हार्दिक शुभकामनाएं! मां लक्ष्मी और भगवान धन्वंतरિ की कृपा से आपके घर में समृद्धि और वाहन में उत्तम ऊर्जा बनी रहे।",
        "gu": "ધનતેરસની હાર્દિક શુભકામનાઓ! આપના જીવનમાં સુખ-સમૃદ્ધિ વધે અને રોયલ એન્ફિલ્ડ રાઇડ સદાય શ્રેષ્ઠ રહે.",
        "en": "May Dhanteras bring boundless prosperity, good health, and pristine performance to your ride!",
    },
    "2026-11-08": {
        "name": "Diwali / Deepawali",
        "significance": "Festival of Lights, Victory of Light over Darkness, and Divine Blessings",
        "theme": "Illuminating your journeys with festive lights, shining chrome, and unshakeable Royal Enfield power",
        "headline": "Happy Diwali - Shubh Deepawali!",
        "hi": "दीपावली की हार्दिक शुभकामनाएं! दीपों का यह पावन पर्व आपके जीवन और हर सफर को खुशियों के उजाले से भर दे।",
        "gu": "દિવાળીની હાર્દિક શુભેચ્છાઓ! રોશનીના આ મહાપર્વે આપનું અને આપના પરિવારનું જીવન સુખ, શાંતિ અને સમૃદ્ધિથી ઝળહળે.",
        "en": "Wishing you and your family a luminous, prosperous, and thrilling Diwali!",
    },
    "2026-11-09": {
        "name": "Gujarati New Year (Bestu Varas / Saal Mubarak)",
        "significance": "Auspicious New Year, fresh beginnings, prosperity, and blessings of elders & deities",
        "theme": "Starting the New Year with Maa Chamunda's blessings and a well-tuned Royal Enfield engine",
        "headline": "Nutan Varshabhinandan - Saal Mubarak!",
        "hi": "नूतन वर्षाभिनंदन! नया साल आपके जीवन में नई ऊर्जा, उत्तम स्वास्थ्य और सुरक्षित यात्राएं लेकर आए।",
        "gu": "નૂતન વર્ષાભિનંદન! નવું વર્ષ આપના માટે સુખ, શાંતિ, સમૃદ્ધિ અને સદાબહાર સવારીઓ લઈને આવે એવી મા ચામુંડાના ચરણોમાં પ્રાર્થના. સાલ મુબારક!",
        "en": "Saal Mubarak & Happy New Year! May this new chapter bring unshakeable milestones and memorable tours on your Royal Enfield!",
    },
    "2026-11-10": {
        "name": "Bhai Dooj",
        "significance": "Celebrating brotherly protection, love, and family warmth",
        "theme": "Brotherhood, festive family road trips on Royal Enfield",
        "headline": "Happy Bhai Dooj!",
        "hi": "भाई दूज की हार्दिक शुभकामनाएं! भाई-बहन के इस पावन पर्व पर आपकी हर यात्रा प्रेम और सुरक्षा से भरी हो।",
        "gu": "ભાઈબીજની હાર્દિક શુભકામનાઓ! ભાઈ-બહેનના અતૂટ પ્રેમ અને સુરક્ષાનું આ પાવન પર્વ સદાય ઉજ્વળ રહે.",
        "en": "Celebrating the enduring bond of protection and brotherhood on every road!",
    },
    "2026-11-14": {
        "name": "Labh Pancham",
        "significance": "Auspicious day for opening shops, workshops, businesses, and initiating work",
        "theme": "Chamunda Automobile workshop opening with divine puja, ready to serve all Royal Enfield riders",
        "headline": "Shubh Labh Pancham!",
        "hi": "लाभ पंचम की हार्दिक शुभकामनाएं! आपके व्यापार और जीवन में निरंतर लाभ और बरकत बनी रहे।",
        "gu": "લાભ પાંચમની હાર્દિક શુભેચ્છાઓ! ધંધા-રોજગારમાં અવિરત પ્રગતિ થાય અને મા ચામુંડાના આશીર્વાદ સદાય રહે.",
        "en": "Wishing everyone prosperity and growth on the auspicious occasion of Labh Pancham!",
    },
    # 2027
    "2027-01-01": {
        "name": "New Year 2027",
        "significance": "Fresh Year, new aspirations, new highways, and new adventures",
        "theme": "New year riding resolutions, long tours, and top-tier Royal Enfield maintenance",
        "headline": "Happy New Year 2027!",
        "hi": "नव वर्ष 2027 की हार्दिक शुभकामनाएं! नई मंजिलें, नए रास्ते और रॉयल एनफील्ड के साथ नए रोमांचक सफर!",
        "gu": "નવા વર્ષ 2027 ની હાર્દિક શુભકામનાઓ! નવી સવારીઓ, નવી મંજિલો અને રોયલ અંદાજ.",
        "en": "Wishing all riders an adventurous and triumphant New Year 2027!",
    },
    "2027-01-14": {
        "name": "Makar Sankranti / Uttarayan 2027",
        "significance": "Festival of Sun transit, kites, joy, and open-road celebration",
        "theme": "Open road touring on Royal Enfield, festive riding freedom",
        "headline": "Happy Makar Sankranti 2027!",
        "hi": "मकर संक्रांति की हार्दिक शुभकामनाएं! आपकी हर यात्रा नई ऊर्जा से भरपूर हो।",
        "gu": "મકર સંક્રાંતિ અને ઉત્તરાયણની હાર્દિક શુભકામનાઓ!",
        "en": "Wishing all Royal Enfield riders a soaring Makar Sankranti!",
    },
}


class FestivalDetector:
    """
    Detects Indian, Hindu, and Gujarati festivals for today or any given date.
    Uses pre-computed calendar + live Gemini AI evaluator for complete accuracy.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model_name = model_name or config.GEMINI_MODEL
        self.history_file = HISTORY_FILE
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_history(self) -> Dict[str, Any]:
        if not self.history_file.exists():
            return {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def is_campaign_posted(self, date_str: str, festival_name: str) -> bool:
        """Checks if a campaign for this festival has already been posted on this date."""
        history = self._read_history()
        key = f"{date_str}::{festival_name.lower().strip()}"
        return key in history

    def mark_campaign_posted(
        self, date_str: str, festival_name: str, media_paths: List[str]
    ) -> None:
        """Records a successful campaign run to prevent duplicate posts."""
        history = self._read_history()
        key = f"{date_str}::{festival_name.lower().strip()}"
        history[key] = {
            "date": date_str,
            "festival": festival_name,
            "posted_at": datetime.datetime.now().isoformat(),
            "media_files": [str(p) for p in media_paths],
            "status": "PUBLISHED",
        }
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            logger.info(f"✅ Recorded festival campaign completion for {festival_name} on {date_str}")
        except Exception as e:
            logger.warning(f"Could not update festival history: {e}")

    def query_gemini_for_festival(self, date_str: str) -> Optional[FestivalInfo]:
        """Queries Gemini using candidate model cascade to detect any unlisted festival for a given date."""
        if not self.api_key:
            return None

        prompt = f"""
You are an expert on Indian festivals, Hindu Panchang, Gujarati cultural events, and national celebrations.
Evaluate the date: {date_str}.

Is this date a recognized festival, auspicious day, Jayanti, or celebration in India (especially Gujarat/North India)?
For example: Vishwakarma Puja, Navratri, Dussehra, Dhanteras, Diwali, Ganesh Chaturthi, Janmashtami, Maha Shivratri, Makar Sankranti, Raksha Bandhan, Guru Purnima, Republic Day, Independence Day, etc.

Return ONLY a valid JSON object matching this schema:
{{
  "is_festival": true,
  "festival_name": "Official Name of Festival",
  "significance": "Brief cultural significance",
  "motorcycle_theme": "How this relates to vehicle blessing, machinery reverence, Royal Enfield touring, or rider brotherhood",
  "greeting_headline": "Happy [Festival Name]!",
  "blessing_message_hi": "Festive blessing in clean Hindi wishing happiness, safe riding, and machine blessings",
  "blessing_message_gu": "Festive blessing in clean Gujarati wishing happiness, safe riding, and machine blessings",
  "blessing_message_en": "Festive blessing in English"
}}

If it is an ordinary day with no notable festival or celebration, return:
{{
  "is_festival": false,
  "festival_name": "",
  "significance": "",
  "motorcycle_theme": "",
  "greeting_headline": "",
  "blessing_message_hi": "",
  "blessing_message_gu": "",
  "blessing_message_en": ""
}}
"""
        from google import genai
        client = genai.Client(api_key=self.api_key)
        candidate_models = get_candidate_models(preferred=self.model_name, tier="argon")

        for model in candidate_models:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                data = json.loads(res.text)
                if data.get("is_festival") and data.get("festival_name"):
                    data["date_str"] = date_str
                    return FestivalInfo(**data)
                return None
            except Exception as e:
                logger.debug(f"Gemini festival check with model {model} failed: {e}")

        return None

    def get_festival_for_date(
        self,
        target_date: Optional[datetime.date] = None,
        use_ai_fallback: bool = True,
    ) -> Optional[FestivalInfo]:
        """
        Determines if the specified date (defaults to today) is a festival.
        First checks curated calendar, then queries Gemini AI if needed.
        """
        d = target_date or datetime.date.today()
        date_str = d.strftime("%Y-%m-%d")

        # 1. Curated Calendar Check
        if date_str in CURATED_FESTIVALS:
            f = CURATED_FESTIVALS[date_str]
            return FestivalInfo(
                is_festival=True,
                festival_name=f["name"],
                date_str=date_str,
                significance=f["significance"],
                motorcycle_theme=f["theme"],
                greeting_headline=f["headline"],
                blessing_message_hi=f["hi"],
                blessing_message_gu=f["gu"],
                blessing_message_en=f["en"],
            )

        # 2. Dynamic Gemini AI Fallback Check
        if use_ai_fallback:
            ai_fest = self.query_gemini_for_festival(date_str)
            if ai_fest and ai_fest.is_festival:
                return ai_fest

        return None

    def get_upcoming_festivals(
        self,
        days: int = 60,
        start_date: Optional[datetime.date] = None,
        use_ai_fallback: bool = False,
    ) -> List[FestivalInfo]:
        """Lists all festivals coming up in the next N days."""
        start = start_date or datetime.date.today()
        upcoming: List[FestivalInfo] = []
        for i in range(days):
            cur = start + datetime.timedelta(days=i)
            fest = self.get_festival_for_date(cur, use_ai_fallback=use_ai_fallback)
            if fest:
                upcoming.append(fest)
        return upcoming
