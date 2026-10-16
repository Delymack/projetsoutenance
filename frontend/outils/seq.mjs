import puppeteer from 'puppeteer-core';
import fs from 'fs';

const OUT = process.env.OUT || '/tmp/opencode/diag2';

function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function seqSVG({width=1500, lifelines, messages, altNote}){
  const margin=170, top=24, boxH=48, rowH=46, gapTop=52, bottom=44;
  const n=lifelines.length;
  const step = n>1 ? (width-2*margin)/(n-1) : 0;
  const X = i => margin + i*step;
  const H = top+boxH+gapTop + messages.length*rowH + (altNote?56:0) + bottom;
  let s=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${H}" font-family="Helvetica, Arial, sans-serif">`;
  s+=`<rect width="${width}" height="${H}" fill="#ffffff"/>`;
  // lifelines
  for(let i=0;i<n;i++){
    s+=`<line x1="${X(i)}" y1="${top+boxH}" x2="${X(i)}" y2="${H-bottom+10}" stroke="#9aa0a6" stroke-width="1.2" stroke-dasharray="5,4"/>`;
  }
  // participant boxes
  for(let i=0;i<n;i++){
    const w=Math.max(150, lifelines[i].length*8.2+28), h=boxH;
    s+=`<rect x="${X(i)-w/2}" y="${top}" width="${w}" height="${h}" rx="7" fill="#D2E3FC" stroke="#1a73e8" stroke-width="1.3"/>`;
    s+=`<text x="${X(i)}" y="${top+h/2+5}" text-anchor="middle" font-size="15" font-weight="600" fill="#174ea6">${esc(lifelines[i])}</text>`;
  }
  let y=top+boxH+gapTop;
  let arrow = (from,to,label,type)=>{
    const x1=X(from), x2=X(to), ty=y-7;
    const col = type==='return' ? '#5f6368' : '#1a73e8';
    const dash = type==='return' ? '6,4' : '0';
    s+=`<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${col}" stroke-width="1.6" stroke-dasharray="${dash}"/>`;
    const dir = x2>x1?1:-1, hs=9;
    s+=`<polygon points="${x2},${y} ${x2-dir*hs},${y-5} ${x2-dir*hs},${y+5}" fill="${col}"/>`;
    const mx=(x1+x2)/2;
    s+=`<text x="${mx}" y="${ty}" text-anchor="middle" font-size="13" fill="#202124">${esc(label)}</text>`;
    y+=rowH;
  };
  let self=(i,label)=>{
    const x=X(i), w=54, h=26, col='#1a73e8';
    s+=`<path d="M ${x} ${y} h ${w} v ${h} h ${-w}" fill="none" stroke="${col}" stroke-width="1.6"/>`;
    s+=`<polygon points="${x},${y+h} ${x+8},${y+h-5} ${x+8},${y+h+5}" fill="${col}"/>`;
    s+=`<text x="${x+w+8}" y="${y+9}" font-size="13" fill="#202124">${esc(label)}</text>`;
    y+=rowH+8;
  };
  for(const m of messages){
    if(m.self){ self(m.from, m.label); }
    else { arrow(m.from, m.to, m.label, m.type||'call'); }
  }
  if(altNote){
    s+=`<rect x="30" y="${y-8}" width="${width-60}" height="${altNote.length*18+18}" rx="6" fill="#FEF7E0" stroke="#F9AB00"/>`;
    altNote.forEach((line,k)=>{ s+=`<text x="46" y="${y+16+k*18}" font-size="13" fill="#8a5300"><tspan font-weight="700">alt</tspan>  ${esc(line)}</text>`; });
  }
  s+='</svg>';
  return {svg:s, width, height:H};
}

const diagrams = {
  '5-2_seq_vente': {
    lifelines:['Vendeur','Système'],
    messages:[
      {from:0,to:1,label:"s'authentifier(identifiants)"},
      {from:1,to:0,label:'confirmation', type:'return'},
      {from:0,to:1,label:'sélectionner le client'},
      {from:0,to:1,label:'ajouter produit + quantité'},
      {self:true,from:1,label:'vérifier la disponibilité'},
      {self:true,from:1,label:'rechercher une promotion valide'},
      {self:true,from:1,label:'calculer le montant'},
      {from:1,to:0,label:'demander validation'},
      {from:0,to:1,label:'confirmer'},
      {self:true,from:1,label:'enregistrer la vente et ses lignes'},
      {self:true,from:1,label:'décrémenter le stock'},
      {from:1,to:0,label:'retourner le récapitulatif', type:'return'},
    ],
    altNote:['[stock insuffisant] le système refuse la vente et affiche un message d\u2019erreur'],
  },
  '5-3_seq_commande': {
    lifelines:['Client','Système'],
    messages:[
      {from:0,to:1,label:"s'authentifier"},
      {from:0,to:1,label:'consulter le catalogue (prix remisés)'},
      {from:1,to:0,label:'liste des produits', type:'return'},
      {from:0,to:1,label:'valider le panier'},
      {from:0,to:1,label:'choisir le mode de paiement'},
      {self:true,from:1,label:'vérifier le stock'},
      {self:true,from:1,label:'créer la commande'},
      {from:1,to:0,label:'confirmer après paiement', type:'return'},
    ],
    altNote:['[stock insuffisant] la commande n\u2019est pas créée'],
  },
  '5-4_seq_promotion': {
    lifelines:['Administrateur','Système'],
    messages:[
      {from:0,to:1,label:"s'authentifier"},
      {from:0,to:1,label:'saisir nom, type de remise, valeur, dates, produits'},
      {self:true,from:1,label:'contrôler la cohérence'},
      {self:true,from:1,label:'enregistrer la promotion'},
      {from:1,to:0,label:'confirmer la création', type:'return'},
    ],
    altNote:['[données invalides] le système retourne les erreurs sans enregistrer'],
  },
  '5-5_seq_production': {
    lifelines:['Vendeur / Admin','Système'],
    messages:[
      {from:0,to:1,label:"s'authentifier"},
      {from:0,to:1,label:'saisir la production (produit, quantité)'},
      {self:true,from:1,label:'mettre à jour la quantité en stock'},
      {from:1,to:0,label:'confirmer l\u2019entrée en stock', type:'return'},
    ],
  },
  '6-2_seq_conception_cmd': {
    lifelines:['UI Client','Contrôleur API','Service Commande','Service Paiement','Dépôts','PostgreSQL'],
    messages:[
      {from:0,to:1,label:'passerCommande(panier)'},
      {from:1,to:2,label:'créerCommande(panier)'},
      {from:2,to:4,label:'verifierStock(produits)'},
      {from:4,to:5,label:'SELECT quantite'},
      {from:5,to:4,label:'quantités', type:'return'},
      {from:2,to:4,label:'enregistrer(commande)'},
      {from:4,to:5,label:'INSERT commande + lignes'},
      {from:2,to:3,label:'payer(montant, mode)'},
      {from:3,to:0,label:'confirmation de paiement', type:'return'},
      {from:1,to:0,label:'commande confirmée', type:'return'},
    ],
  },
  '6-3_seq_conception_promo': {
    lifelines:['UI Admin','Contrôleur API','Service Promotion','Dépôt','PostgreSQL'],
    messages:[
      {from:0,to:1,label:'créerPromotion(données)'},
      {from:1,to:2,label:'valider(données)'},
      {self:true,from:2,label:'vérifier les règles (dates, valeur, produits)'},
      {from:2,to:3,label:'enregistrer(promotion)'},
      {from:3,to:4,label:'INSERT promotion'},
      {from:1,to:0,label:'promotion créée', type:'return'},
    ],
    altNote:['[données invalides] ServicePromotion retourne les erreurs, aucune écriture'],
  },
};

const b=await puppeteer.launch({executablePath:'/usr/bin/chromium-browser',headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
for(const [name,spec] of Object.entries(diagrams)){
  const {svg,width,height}=seqSVG(spec);
  const p=await b.newPage();
  await p.setViewport({width:width+40, height:height+40, deviceScaleFactor:2});
  await p.setContent(`<body style="margin:0;padding:0">${svg}</body>`,{waitUntil:'load'});
  const el=await p.$('svg'); await el.screenshot({path:`${OUT}/${name}.png`});
  await p.close();
  console.log(name, width+'x'+height);
}
await b.close();
