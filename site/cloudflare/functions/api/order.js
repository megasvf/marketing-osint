// Cloudflare Pages Function: POST /api/order
// Takes the order form, creates a Plata by mono invoice and sends the buyer to the mono payment page.
// No database: the order details travel in the invoice (destination + comment), so they show up in the
// monobank business app next to the payment. After payment mono redirects the buyer to /thanks.html (or /uk/thanks.html).
//
// Cloudflare Pages settings → Environment variables (encrypt the token):
//   MONO_TOKEN  X-Token from the monobank business cabinet (internet acquiring / Plata by mono)
//   PRICE_KOP   price in kopiyky, e.g. 199000 for 1 990 UAH
// Optional: VALIDITY_SEC (default 3600), BASKET=1 to send a one-line basketOrder for automatic fiscal receipts.

const RELATIONSHIPS = ["competitor", "benchmark", "prospect", "partner", "self"];
const DOMAIN = /^(?!-)(?:[a-z0-9-]{1,63}\.)+[a-z]{2,24}$/;
const EMAIL = /^[^\s@<>]{1,64}@[^\s@<>]{1,190}\.[a-z]{2,24}$/i;

function back(origin, lang, code) {
  const base = lang === "uk" ? "/uk/order.html" : "/order.html";
  return Response.redirect(`${origin}${base}?error=${code}#form`, 303);
}

function cleanDomain(v) {
  return String(v || "").trim().toLowerCase()
    .replace(/^https?:\/\//, "").replace(/^www\./, "").split(/[/?#\s]/)[0];
}

export async function onRequestPost({ request, env }) {
  const origin = new URL(request.url).origin;
  let form;
  try { form = await request.formData(); } catch { return back(origin, "en", "form"); }
  const lang = form.get("lang") === "uk" ? "uk" : "en";
  if (form.get("company_fax")) return back(origin, lang, "form");           // honeypot: bots fill every field
  const domain = cleanDomain(form.get("domain"));
  const rel = String(form.get("relationship") || "");
  const email = String(form.get("email") || "").trim();
  const notes = String(form.get("notes") || "").replace(/\s+/g, " ").trim().slice(0, 300);
  if (!DOMAIN.test(domain)) return back(origin, lang, "domain");
  if (!RELATIONSHIPS.includes(rel)) return back(origin, lang, "relationship");
  if (!EMAIL.test(email)) return back(origin, lang, "email");
  if (form.get("consent") !== "yes") return back(origin, lang, "consent");
  const amount = parseInt(env.PRICE_KOP, 10);
  if (!env.MONO_TOKEN || !Number.isInteger(amount) || amount <= 0) return back(origin, lang, "config");

  const reference = `osint-${Date.now().toString(36)}-${crypto.randomUUID().slice(0, 8)}`;
  const title = `Marketing OSINT report: ${domain}`;
  const info = {
    reference,
    destination: title.slice(0, 280),
    comment: `${domain} | ${rel} | ${email} | ${lang}${notes ? " | " + notes : ""}`.slice(0, 280),
    customerEmails: [email],
  };
  if (env.BASKET === "1") {
    info.basketOrder = [{ name: title.slice(0, 128), qty: 1, sum: amount, total: amount, code: "osint-report", unit: "шт." }];
  }
  const body = {
    amount, ccy: 980, merchantPaymInfo: info,
    redirectUrl: `${origin}${lang === "uk" ? "/uk" : ""}/thanks.html`,
    validity: parseInt(env.VALIDITY_SEC || "3600", 10),
    paymentType: "debit",
  };
  let res, data;
  try {
    res = await fetch("https://api.monobank.ua/api/merchant/invoice/create", {
      method: "POST", headers: { "X-Token": env.MONO_TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    data = await res.json();
  } catch {
    return back(origin, lang, "payment");
  }
  if (!res.ok || !data.pageUrl) {
    console.log("mono invoice/create failed", res.status, JSON.stringify(data).slice(0, 300));  // shows in Pages logs, no buyer data
    return back(origin, lang, "payment");
  }
  return Response.redirect(data.pageUrl, 303);
}

export function onRequestGet({ request }) {
  return Response.redirect(new URL("/order.html", request.url).toString(), 303);
}
