import type { UiLang } from "../i18n";

/** A string in English with an optional Hinglish version (falls back to English). */
export interface Text { en: string; hinglish?: string }
export const pick = (lang: UiLang, v: Text) => v[lang] ?? v.en;

export interface Step { title: Text; body: Text; icon: string }
export interface Chapter { id: string; title: Text; intro?: Text; steps: Text[]; tip?: Text }

// --------------------------------------------------------------------------- first-login tour

export const REP_TOUR: Step[] = [
  { icon: "mic", title: { en: "Welcome to BolBazaar", hinglish: "BolBazaar mein swagat hai" },
    body: { en: "You talk, the app writes the visit for you: retailer, order, payment and follow-ups. No forms. This 1-minute tour shows how.",
            hinglish: "Aap bolte ho, app visit likh deta hai: retailer, order, payment aur follow-ups. Koi form nahi. Ye 1 minute ka tour dikhata hai kaise." } },
  { icon: "mic", title: { en: "1. Log a visit", hinglish: "1. Visit log karo" },
    body: { en: "Tap the big red microphone in the middle of the bottom bar, then speak about the visit. Say the retailer, what they ordered with quantity, any payment, and promises. Can't talk? Choose “Type it”.",
            hinglish: "Neeche beech ka bada laal mic dabao aur visit ke baare mein bolo. Retailer ka naam, kya order hua (quantity ke saath), payment, aur vaade batao. Bol nahi sakte? “Type it” chuno." } },
  { icon: "list", title: { en: "2. Check and confirm", hinglish: "2. Check karo aur confirm karo" },
    body: { en: "You get a clear list to review. Nothing is saved until you tap Confirm, so you can always fix things first or discard the draft.",
            hinglish: "Aapko review ke liye ek saaf list milti hai. Confirm dabane tak kuch save nahi hota, isliye pehle theek kar sakte ho ya draft discard kar sakte ho." } },
  { icon: "spark", title: { en: "3. Fix things by voice", hinglish: "3. Awaaz se theek karo" },
    body: { en: "If the app is unsure it asks one short question: tap an answer, or tap Edit, hold the mic and say it, for example “Parle-G 15 kar do” or “delivery Monday”.",
            hinglish: "Agar app ko kuch samajh na aaye to ek chhota sawal poochta hai: jawab chuno, ya Edit dabao, mic pakad ke bolo, jaise “Parle-G 15 kar do” ya “delivery Monday”." } },
  { icon: "box", title: { en: "4. Item not in the catalogue?", hinglish: "4. Item catalogue mein nahi hai?" },
    body: { en: "Tap “+ Add as a new item”, or say “add karo, 60 rupaye kilo”. The item and its price are added to the catalogue when you confirm the visit.",
            hinglish: "“+ Add as a new item” dabao, ya bolo “add karo, 60 rupaye kilo”. Visit confirm karte hi item aur uska price catalogue mein add ho jata hai." } },
  { icon: "more", title: { en: "5. Help is always in “More”", hinglish: "5. Madad hamesha “More” mein hai" },
    body: { en: "Open More for the full manual, to replay this tour, change language, or report a bug. You're ready: tap the red mic to log your first visit.",
            hinglish: "Poora manual, ye tour dobara dekhna, bhasha badalna ya bug report karna ho to More kholo. Aap taiyaar ho: pehla visit log karne ke liye laal mic dabao." } },
];

export const MANAGER_TOUR: Step[] = [
  { icon: "home", title: { en: "Welcome to BolBazaar", hinglish: "BolBazaar mein swagat hai" },
    body: { en: "Your team talks; you see verified visits, orders, payments and promises here. This short tour covers the main pages.",
            hinglish: "Aapki team bolti hai; aap yahan verified visits, orders, payments aur vaade dekhte ho. Ye chhota tour mukhya pages dikhata hai." } },
  { icon: "chart", title: { en: "Overview", hinglish: "Overview" },
    body: { en: "Today's order value, visits, outstanding payments and the team's conversion. Click any card or “View all” link to go deeper.",
            hinglish: "Aaj ki order value, visits, baaki payment aur team ka conversion. Kisi card ya “View all” par click karke detail dekho." } },
  { icon: "spark", title: { en: "Ask", hinglish: "Poochho" },
    body: { en: "Type a question like “Which retailers have overdue payments?”. The answer comes from your data, never from AI guesses.",
            hinglish: "“Which retailers have overdue payments?” jaisa sawal likho. Jawab aapke data se aata hai, AI ke andaaze se nahi." } },
  { icon: "list", title: { en: "Catalogue and prices", hinglish: "Catalogue aur prices" },
    body: { en: "Add items one by one, or hold the mic and read out a whole list (“chawal 60 rupaye kilo, atta 45 rupaye kilo…”). Review the table, then add. Changing a price affects new orders only.",
            hinglish: "Items ek-ek karke jodo, ya mic pakad ke poori list bolo (“chawal 60 rupaye kilo, atta 45 rupaye kilo…”). Table check karo, phir add karo. Price badalne se sirf naye orders par asar hota hai." } },
  { icon: "flag", title: { en: "Promises, retailers, team", hinglish: "Vaade, retailers, team" },
    body: { en: "Promises lists open follow-ups (tap Done when completed). Retailers shows who owes money. Team compares your executives.",
            hinglish: "Promises mein khule follow-ups hain (poora hone par Done dabao). Retailers mein kiska paisa baaki hai. Team mein executives ki tulna hai." } },
  { icon: "alert", title: { en: "Help and bug reports", hinglish: "Help aur bug report" },
    body: { en: "Open Help & manual in the menu for step-by-step instructions, to replay this tour, or to report a bug.",
            hinglish: "Menu mein Help & manual kholo: step-by-step guide, ye tour dobara dekhna, ya bug report karna." } },
];

// --------------------------------------------------------------------------- manual

export const REP_MANUAL: Chapter[] = [
  { id: "start", title: { en: "1. Getting started", hinglish: "1. Shuru karna" },
    steps: [
      { en: "Open the app and sign in with your username and password. New here? Choose Sign up, enter your name, a username (3 to 32 letters/digits), a password of at least 8 characters, and your territory." ,
        hinglish: "App kholo aur username aur password se sign in karo. Naye ho? Sign up chuno: naam, username (3 se 32 akshar/ank), kam se kam 8 akshar ka password aur apni territory daalo." },
      { en: "Pick your app language with the EN / हिं switch (in More). This only changes the app's words; you can speak Hindi, English or Hinglish." ,
        hinglish: "EN / हिं switch (More mein) se app ki bhasha chuno. Isse sirf app ke shabd badalte hain; aap Hindi, English ya Hinglish bol sakte ho." },
      { en: "The first time you sign in a short tour starts. You can replay it any time from More → Take the tour." ,
        hinglish: "Pehli baar sign in karne par chhota tour shuru hota hai. Kabhi bhi More → Take the tour se dobara dekh sakte ho." },
    ] },
  { id: "log", title: { en: "2. Log your first visit", hinglish: "2. Pehla visit log karo" },
    steps: [
      { en: "Tap the red microphone in the middle of the bottom bar (or “Log a Visit” on Today).", hinglish: "Neeche beech ka laal mic (ya Today par “Log a Visit”) dabao." },
      { en: "Allow microphone access if your phone asks.", hinglish: "Phone microphone ki permission maange to Allow karo." },
      { en: "Press and hold the mic (or tap once to start and again to stop) and speak naturally about the visit.", hinglish: "Mic dabake pakdo (ya ek baar dabao shuru karne ke liye aur dobara rokne ke liye) aur aaram se visit ke baare mein bolo." },
      { en: "Release to send. Wait a few seconds while the app listens, understands and matches names.", hinglish: "Bhejne ke liye chhodo. Kuch second ruko jab tak app sunta, samajhta aur naam match karta hai." },
      { en: "No microphone or noisy place? Tap “Can't talk? Type it” and type the same sentence. “Try a sample visit” shows a demo.", hinglish: "Mic nahi hai ya shor hai? “Can't talk? Type it” dabao aur wahi vaakya type karo. “Try a sample visit” demo dikhata hai." },
    ],
    tip: { en: "Speak close to the phone, one visit at a time, and keep it under 2 minutes.", hinglish: "Phone ke paas bolo, ek baar mein ek visit, aur 2 minute se kam rakho." } },
  { id: "say", title: { en: "3. What to say", hinglish: "3. Kya bolna hai" },
    steps: [
      { en: "Retailer + order: “Sharma General Store gaya tha, bees packet Parle-G aur das bottle Real juice kal bhej dena.”", hinglish: "Retailer + order: “Sharma General Store gaya tha, bees packet Parle-G aur das bottle Real juice kal bhej dena.”" },
      { en: "Payment: “Woh paanch hazaar rupaye kal dega.” (promised) or “Teen hazaar mile.” (received)", hinglish: "Payment: “Woh paanch hazaar rupaye kal dega.” (vaada) ya “Teen hazaar mile.” (mil gaye)" },
      { en: "Follow-up: “Agle Monday ko dobara visit karna hai.”", hinglish: "Follow-up: “Agle Monday ko dobara visit karna hai.”" },
      { en: "Complaint: “Biscuit ke kuch packets damaged the.”", hinglish: "Complaint: “Biscuit ke kuch packets damaged the.”" },
      { en: "Always say a quantity and a date when you can; the app will ask if you forget.", hinglish: "Jahan ho sake quantity aur tareekh bolo; bhool gaye to app poochh lega." },
    ] },
  { id: "review", title: { en: "4. Review, answer, confirm", hinglish: "4. Review, jawab, confirm" },
    steps: [
      { en: "The Review screen lists Retailer, Order (items, total), Delivery, Payment and Follow-ups. Tap a row to expand it. “You said” shows what the app heard.", hinglish: "Review screen par Retailer, Order (items, total), Delivery, Payment aur Follow-ups dikhte hain. Row dabao to khulti hai. “You said” mein dikhta hai app ne kya suna." },
      { en: "A red card “Check one thing” means the app needs one answer. Tap an option, or type a number or date. “Hear it” reads the question aloud.", hinglish: "Laal card “Check one thing” ka matlab app ko ek jawab chahiye. Option dabao, ya number/tareekh type karo. “Hear it” sawal sunata hai." },
      { en: "When no questions are left, tap Confirm. The visit, order, payments and follow-ups are saved and the app says a short confirmation.", hinglish: "Jab koi sawal na bache to Confirm dabao. Visit, order, payment aur follow-ups save ho jate hain aur app chhoti confirmation bolta hai." },
      { en: "Changed your mind? Tap Edit → Discard draft. Nothing is saved.", hinglish: "Mann badal gaya? Edit → Discard draft dabao. Kuch save nahi hoga." },
    ],
    tip: { en: "Prices always come from the catalogue on the server, not from what was said.", hinglish: "Price hamesha server ke catalogue se aata hai, bole hue se nahi." } },
  { id: "fix", title: { en: "5. Correct by voice", hinglish: "5. Awaaz se sudhaaro" },
    steps: [
      { en: "On the Review screen tap Edit. Hold the mic and say the fix, or type it.", hinglish: "Review screen par Edit dabao. Mic pakad ke sudhaar bolo, ya type karo." },
      { en: "Examples: “Parle-G 15 kar do”, “Real juice hata do”, “delivery Monday ko”, “payment saat hazaar”, “priority high kar do”.", hinglish: "Udaharan: “Parle-G 15 kar do”, “Real juice hata do”, “delivery Monday ko”, “payment saat hazaar”, “priority high kar do”." },
      { en: "The list updates and shows what changed. If the app cannot do something it says so; use the buttons or type instead.", hinglish: "List update hoti hai aur dikhati hai kya badla. Agar app kuch nahi kar pata to batata hai; tab buttons ya type ka use karo." },
    ] },
  { id: "newitem", title: { en: "6. An item is not in the catalogue", hinglish: "6. Item catalogue mein nahi hai" },
    steps: [
      { en: "The app asks: “… catalogue mein nahi mila.” Pick the matching product if it is the same thing, or add it as new.", hinglish: "App poochta hai: “… catalogue mein nahi mila.” Agar wahi cheez hai to matching product chuno, nahi to naya add karo." },
      { en: "Fastest: tap Edit, hold the mic and say “add karo, 60 rupaye kilo” (price and unit in one go).", hinglish: "Sabse tez: Edit dabao, mic pakdo aur bolo “add karo, 60 rupaye kilo” (price aur unit ek saath)." },
      { en: "Or tap “+ Add … as a new item”. The app then asks for the price (and the unit if you did not say it). Type or say it.", hinglish: "Ya “+ Add … as a new item” dabao. Phir app price poochta hai (aur unit agar na bola ho). Type karo ya bolo." },
      { en: "The item is created in the catalogue only when you tap Confirm. Managers can fix its name or price later.", hinglish: "Item catalogue mein tabhi banta hai jab aap Confirm dabate ho. Manager baad mein naam ya price theek kar sakte hain." },
    ] },
  { id: "offline", title: { en: "7. No internet?", hinglish: "7. Internet nahi hai?" },
    steps: [
      { en: "You can still record. The recording waits in the upload queue (see More) and is sent automatically when you are online.", hinglish: "Aap phir bhi record kar sakte ho. Recording upload queue mein rehti hai (More dekho) aur online aate hi apne aap bhej di jati hai." },
      { en: "Understanding the recording needs a connection, so you review and confirm after it uploads, under “Waiting” on Today.", hinglish: "Recording samajhne ke liye connection chahiye, isliye upload ke baad Today ke “Waiting” mein review aur confirm karo." },
    ] },
  { id: "followups", title: { en: "8. Follow-ups and history", hinglish: "8. Follow-ups aur history" },
    steps: [
      { en: "Today shows what is due. More → Follow-ups lists every open promise. Tap the circle when it is done.", hinglish: "Today mein dikhta hai kya due hai. More → Follow-ups mein har khula vaada hai. Poora hone par circle dabao." },
      { en: "Visits and Orders show everything you have saved.", hinglish: "Visits aur Orders mein aapka sab save kiya hua dikhta hai." },
    ] },
  { id: "trouble", title: { en: "9. If something goes wrong", hinglish: "9. Kuch galat ho jaye to" },
    steps: [
      { en: "“Needs a retry”: the voice or AI service failed. Tap Try again; your recording is kept.", hinglish: "“Needs a retry”: voice ya AI service fail hui. Try again dabao; recording safe hai." },
      { en: "“You have reached your usage limit”: you have used today's or this minute's allowance. Wait for the time shown, or type instead of speaking.", hinglish: "“You have reached your usage limit”: aaj ya is minute ka hissa khatam. Dikhaye samay tak ruko, ya bolne ke bajay type karo." },
      { en: "“Answer first” on Confirm: there is an open question above. Answer it.", hinglish: "Confirm par “Answer first”: upar ek sawal baaki hai. Pehle jawab do." },
      { en: "Anything else: More → Report a bug. Say what you did and what happened.", hinglish: "Kuch aur: More → Report a bug. Batao kya kiya aur kya hua." },
    ] },
];

export const MANAGER_MANUAL: Chapter[] = [
  { id: "start", title: { en: "1. Getting started", hinglish: "1. Shuru karna" },
    steps: [
      { en: "Sign in as a manager. The left menu has Overview, Ask, Visits, Orders, Catalogue, Promises, Retailers, Team and Help.", hinglish: "Manager ke roop mein sign in karo. Left menu mein Overview, Ask, Visits, Orders, Catalogue, Promises, Retailers, Team aur Help hain." },
      { en: "On a phone, open the menu with the ☰ button.", hinglish: "Phone par ☰ button se menu kholo." },
      { en: "A short tour runs the first time; replay it from Help & manual.", hinglish: "Pehli baar chhota tour chalta hai; Help & manual se dobara dekho." },
    ] },
  { id: "overview", title: { en: "2. Overview, Visits, Orders, Team", hinglish: "2. Overview, Visits, Orders, Team" },
    steps: [
      { en: "Overview: today's order value, 30-day visits, outstanding payments, conversion, overdue payments and an activity grid.", hinglish: "Overview: aaj ki order value, 30 din ke visits, baaki payment, conversion, overdue payments aur activity grid." },
      { en: "Visits and Orders list what reps saved. Team compares executives (visits, orders, conversion, open and overdue follow-ups).", hinglish: "Visits aur Orders mein reps ka save kiya hua dikhta hai. Team mein executives ki tulna hai (visits, orders, conversion, khule aur overdue follow-ups)." },
    ] },
  { id: "ask", title: { en: "3. Ask questions", hinglish: "3. Sawal poochho" },
    steps: [
      { en: "Open Ask, type a question or tap a suggestion, for example “Which retailers haven't ordered in 30 days?”.", hinglish: "Ask kholo, sawal likho ya suggestion dabao, jaise “Which retailers haven't ordered in 30 days?”." },
      { en: "The answer is computed from your data with a fixed query. Only the supported questions work.", hinglish: "Jawab aapke data se fixed query se nikalta hai. Sirf supported sawal chalte hain." },
    ] },
  { id: "catalogue", title: { en: "4. Catalogue and prices", hinglish: "4. Catalogue aur prices" },
    steps: [
      { en: "Open Catalogue. To add one item: enter Name, Sold by (kg, packet, bottle or piece), Price per unit, optional Units per case and spoken names, then Add to catalogue.", hinglish: "Catalogue kholo. Ek item jodne ke liye: Name, Sold by (kg, packet, bottle ya piece), Price per unit, optional Units per case aur spoken names bharo, phir Add to catalogue." },
      { en: "To change a price or name: Edit on the row, change, Save. Changing a price affects new orders only.", hinglish: "Price ya naam badalne ke liye: row par Edit, badlo, Save. Price badalne se sirf naye orders par asar hota hai." },
      { en: "To remove an item: Retire (Restore brings it back). Old orders keep it.", hinglish: "Item hatane ke liye: Retire (Restore se wapas). Purane orders mein rehta hai." },
      { en: "Set up many items at once: in “Speak or type your whole list”, hold the mic and read the list, or paste it, then Read my list.", hinglish: "Ek saath bahut items: “Speak or type your whole list” mein mic pakad ke list bolo, ya paste karo, phir Read my list." },
      { en: "Check the table that appears: fix names, units and prices, untick rows you don't want, fill what is missing, then Add N items. Nothing is saved before that.", hinglish: "Jo table aaye use check karo: naam, unit, price theek karo, jo nahi chahiye untick karo, jo kam hai bharo, phir Add N items. Usse pehle kuch save nahi hota." },
      { en: "Reps can also add a missing item by voice during a visit; fix any of those here.", hinglish: "Reps visit ke dauraan awaaz se missing item bhi jod sakte hain; unhe yahin theek karo." },
    ],
    tip: { en: "Add other names reps say (chawal, rice) in “Spoken names” so voice matching finds the item.", hinglish: "Reps jo dusre naam bolte hain (chawal, rice) unhe “Spoken names” mein daalo taaki voice matching item dhundh le." } },
  { id: "promises", title: { en: "5. Promises and retailers", hinglish: "5. Vaade aur retailers" },
    steps: [
      { en: "Promises lists open follow-ups with due dates. Tap Done when completed.", hinglish: "Promises mein due date ke saath khule follow-ups hain. Poora hone par Done dabao." },
      { en: "Retailers shows outstanding amounts and the next payment follow-up.", hinglish: "Retailers mein baaki raashi aur agla payment follow-up dikhta hai." },
    ] },
  { id: "admin", title: { en: "6. Admin tools (admin accounts)", hinglish: "6. Admin tools (admin account)" },
    steps: [
      { en: "Bug reports (menu): see what users reported, change status (open, in progress, resolved, won't fix) and leave a note.", hinglish: "Bug reports (menu): users ne kya report kiya dekho, status badlo (open, in progress, resolved, won't fix) aur note likho." },
      { en: "Usage and the emergency switch for the voice/AI services are available to admins through the API; see the security guide.", hinglish: "Usage aur voice/AI services ka emergency switch admins ke liye API se hai; security guide dekho." },
    ] },
  { id: "trouble", title: { en: "7. If something goes wrong", hinglish: "7. Kuch galat ho jaye to" },
    steps: [
      { en: "Use Report a bug (in the menu). Pick what happened, describe it, and keep “Attach technical details” ticked: it helps us find the cause.", hinglish: "Menu mein Report a bug use karo. Kya hua chuno, likho, aur “Attach technical details” ticked rakho: isse karan dhundhne mein madad milti hai." },
      { en: "“Usage limit” and “service is busy” messages clear by themselves; wait for the time shown.", hinglish: "“Usage limit” aur “service is busy” messages apne aap theek ho jate hain; dikhaye samay tak ruko." },
    ] },
];
