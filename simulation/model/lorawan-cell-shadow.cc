/*
 * lorawan-cell-shadow.cc
 *
 * Variante AVEC ombrage de lorawan-cell.cc, pour le projet STOP-MNT.
 *
 * Tout est identique au fichier sans ombrage, a une seule difference : on
 * accroche derriere le modele log-distance un petit modele d'ombrage maison,
 * ecrit ci-dessous, dont l'ecart-type (sigma, en dB) se regle par zone via la
 * ligne de commande.
 *
 * Comportement physique vise : l'ombrage est tire UNE SEULE FOIS par noeud, a
 * sa position, puis conserve. Un noeud place dans un creux y reste. C'est ce
 * qui fait qu'un noeud mal loti decroche vraiment, au lieu d'avoir de la chance
 * un paquet sur deux. L'ombrage est independant d'un noeud a l'autre (pas de
 * correlation spatiale) : simplification assumee, le sigma suffit a fixer le
 * taux de noeuds en difficulte, donc le rayon fiable.
 *
 * Si on passe --shadowingSigma=0, aucun modele d'ombrage n'est accroche : le
 * fichier reproduit alors exactement la version sans ombrage. Pratique comme
 * controle.
 *
 * Borne d'horizon radio : un dernier maillon de la chaine de perte coupe toute
 * reception au-dela de d_horizon = 4,12 (sqrt(h_gw) + sqrt(h_noeud)) km
 * (refraction standard, Terre 4/3). DESACTIVEE par defaut (horizonCoefKm=0) :
 * depuis le 2026-10-25, l'horizon est applique dans l'analyse (masquage des
 * bandes au-dela), pas dans la chaine de pertes. Classe gardee pour reference.
 *
 * Placement : --placement=disque (uniforme en surface, capacite) ou
 * --placement=distance (uniforme en distance, portee).
 *
 * Sortie : une ligne prefixee "CSV;", puis une ligne "NODE;" par noeud (trace
 * par noeud, desactivable par --nodeTrace=0), puis un resume lisible.
 *
 * Colonnes de la ligne NODE :
 *   exp;zone;nDevices;runNumber;confirmed;nodeId;distance_m;sf;
 *   newSent;txTotal;received;acked;airtime_s;gwNearest;gwReceptions;multiGw;
 *   latencyMean_s;latencyMax_s;rxNearest;profile;genRoutine;genAlert;alertNew;
 *   alertDelivered;alertAcked;alertLatUpMax_s;alertRttMean_s;alertRttMax_s;
 *   mobile;readingsGen;readingsDelivered;readingsDropped;readingLatMean_s;readingLatMax_s
 * - distance_m : distance horizontale a la passerelle, en metres.
 * - sf         : facteur d'etalement attribue au noeud.
 * - newSent    : trames nouvelles produites par la MAC du noeud.
 * - txTotal    : emissions radio, retransmissions du confirme comprises.
 * - received   : trames nouvelles recues par au moins une passerelle.
 * - acked      : trames confirmees acquittees (-1 en non confirme).
 * - airtime_s  : temps d'antenne cumule du noeud, en secondes (proxy energie).
 * - gwNearest  : indice de la passerelle la plus proche ; distance_m s'y rapporte.
 * - gwReceptions : receptions par les passerelles, doublons compris.
 * - multiGw    : trames entendues par au moins deux passerelles (diversite).
 * - latencyMean_s, latencyMax_s : emission MAC -> premiere reception passerelle
 *   (-1 si aucune trame recue).
 * - rxNearest  : trames recues par la passerelle la plus proche. received -
 *   rxNearest = trames sauvees par une autre passerelle (gain de diversite).
 * - profile    : indice du profil patient (-1 = emetteur periodique historique).
 * - genRoutine, genAlert : trames produites par l'application. Elles peuvent
 *   depasser newSent : une trame retardee par le cycle de service est ecrasee
 *   par la suivante dans le module (pas de file d'attente).
 * - alertNew, alertDelivered, alertAcked : alertes parties, recues, acquittees.
 * - alertLatUpMax_s : latence montante maximale d'une alerte ; alertRttMean_s,
 *   alertRttMax_s : premiere tentative -> acquittement (-1 / 0 si aucune).
 * Les sommes de newSent et received sur les noeuds egalent sent et received
 * de la ligne CSV : memes sources de trace que le traceur du module.
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/mobility-module.h"
#include "ns3/propagation-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/lorawan-module.h"
#include "ns3/energy-module.h"
#include "stopmnt-propagation.h"

#include <sstream>
#include <vector>
#include <string>
#include <iomanip>
#include <map>
#include <utility>
#include <cmath>
#include <set>
#include <tuple>
#include <deque>
#include <algorithm>
#include <limits>

using namespace ns3;
using namespace lorawan;

NS_LOG_COMPONENT_DEFINE ("LorawanCellShadow");

// Modeles de propagation partages (ombrage par lien, vegetation, horizon) :
// voir stopmnt-propagation.h, inclus plus haut.


// =============================================================================
// Trace par noeud.
//
// Le traceur du module ne donne que des totaux. On ecoute donc les memes
// sources de trace que lui, mais on range les compteurs par noeud :
//   - MAC du noeud "SentNewPacket"             -> trame nouvelle
//   - PHY du noeud "StartSending"              -> emission radio (+ temps d'antenne)
//   - MAC du noeud "ConfirmedTransmissionOutcome" -> acquittement obtenu ou non
//   - MAC de la passerelle "ReceivedPacket"    -> trame recue
// Legere : quelques compteurs par noeud, pas de trace par paquet ecrite.
// =============================================================================
struct NodeStats
{
  uint32_t newSent = 0;
  uint32_t txTotal = 0;
  uint32_t received = 0;
  uint32_t acked = 0;
  double airtimeS = 0.0;
  uint32_t gwReceptions = 0;   // receptions passerelle, doublons compris
  uint32_t multiGw = 0;        // trames entendues par au moins 2 passerelles
  double latencySumS = 0.0;    // emission MAC -> premiere reception passerelle
  double latencyMaxS = 0.0;
  uint32_t rxNearest = 0;      // trames recues par la passerelle la plus proche
  // Profils patients et alerte (application ProfileSender).
  int32_t profile = -1;        // indice du profil, -1 = emetteur periodique historique
  uint32_t genRoutine = 0;     // trames de routine produites par l'application
  uint32_t genAlert = 0;       // alertes produites par l'application
  uint32_t alertNew = 0;       // alertes parties de la MAC (non ecrasees avant emission)
  uint32_t alertDelivered = 0; // alertes recues par au moins une passerelle
  uint32_t alertAcked = 0;     // alertes acquittees (aller-retour reussi)
  double alertLatUpMaxS = 0.0; // emission MAC -> premiere reception passerelle, max
  double alertRttSumS = 0.0;   // premiere tentative -> acquittement, somme
  double alertRttMaxS = 0.0;
  // Mesures (lectures) : une routine produit une mesure. Sans store-and-forward
  // une trame porte une mesure ; avec, une trame peut en porter plusieurs.
  bool mobile = false;
  uint32_t readingsGen = 0;
  uint32_t readingsDelivered = 0;
  uint32_t readingsDropped = 0;   // ecrasees par debordement du tampon
  double readingLatSumS = 0.0;    // production de la mesure -> premiere reception
  double readingLatMaxS = 0.0;
  // Routine confirmee (mode tout confirme) : delai production -> acquittement.
  uint32_t confRoutineGen = 0;    // trames de routine confirmees produites
  uint32_t confRoutineAcked = 0;
  uint32_t confRoutineFail = 0;   // issue negative (nbTrans epuise ou garde)
  double confRoutineDelaySumS = 0.0;
  double confRoutineDelayMaxS = 0.0;
  double energyJ = -1.0;          // energie radio consommee (modele du module), -1 si non mesuree
  // Consignes v6 : recapitulatif quotidien et alarmes techniques du pont.
  uint32_t recapAttempts = 0;     // montees portant une demande de recapitulatif
  uint32_t recapOk = 0;           // recapitulatifs recus
  uint32_t techAlarms = 0;        // alarmes techniques (recapitulatif absent, tampon plein)
  uint32_t resent = 0;            // mesures renvoyees apres un recapitulatif
};

static std::map<uint32_t, NodeStats> g_nodeStats;

// Mise en sommeil du PHY d'un noeud. RequestSleepMode est protegee dans le
// module : on prend son adresse via une classe derivee (acces legal), sans
// modifier le module.
struct PhySleepAccess : public EndDeviceLoraPhy
{
  static void (EndDeviceLoraPhy::*Get ()) ()
  {
    return &PhySleepAccess::RequestSleepMode;
  }
};
static void
PhySleep (Ptr<EndDeviceLoraPhy> phy)
{
  ((*phy).*PhySleepAccess::Get ()) ();
}

// Trames confirmees, une entree par trame : delai production -> acquittement.
// kind 0 routine, 1 alerte. Une trame sans issue a la fin compte comme non
// acquittee (delai infini) dans les percentiles.
struct ConfFrame
{
  uint32_t node;
  int kind;
  double tProd;
  bool done = false;
  bool acked = false;
  double delay = -1.0;
};
static std::vector<ConfFrame> g_confFrames;
static std::map<Ptr<const Packet>, size_t> g_confIndex;
static uint32_t g_guardFires = 0;    // gardes declenchees (issue jamais signalee)
static uint32_t g_requeued = 0;      // routines confirmees interrompues par une alerte, renvoyees

static void
ConfRegister (Ptr<const Packet> p, uint32_t node, int kind, double tProd)
{
  g_confIndex[p] = g_confFrames.size ();
  g_confFrames.push_back (ConfFrame{node, kind, tProd});
}

static void
ConfClose (Ptr<const Packet> p, bool ack)
{
  auto it = g_confIndex.find (p);
  if (it == g_confIndex.end ())
    {
      return;
    }
  ConfFrame &f = g_confFrames[it->second];
  if (f.done)
    {
      return;
    }
  f.done = true;
  f.acked = ack;
  if (ack)
    {
      f.delay = Simulator::Now ().GetSeconds () - f.tProd;
    }
  if (f.kind == 0)
    {
      NodeStats &s = g_nodeStats[f.node];
      if (ack)
        {
          s.confRoutineAcked++;
          s.confRoutineDelaySumS += f.delay;
          s.confRoutineDelayMaxS = std::max (s.confRoutineDelayMaxS, f.delay);
        }
      else
        {
          s.confRoutineFail++;
        }
    }
}

// Suivi des mesures : (noeud, numero) portees par chaque trame, instant de
// production, livraison. Detail conserve pour les noeuds mobiles.
struct Reading
{
  double tGen;
  double x, y;
  bool delivered;
  double tDeliv;
  bool dropped;
};
static std::map<uint32_t, std::vector<Reading>> g_readings;
static std::map<Ptr<const Packet>, std::vector<std::pair<uint32_t, uint32_t>>> g_frameReadings;

// Trace par trame, pour les noeuds mobiles seulement (petits cas).
struct PktRec
{
  uint32_t node;
  double t, x, y, dNear;
  int nearGw, sf, kind, nReadings;
  bool delivered = false;
  double lat = -1.0;
  std::set<uint32_t> gws;
};
static std::map<Ptr<const Packet>, PktRec> g_pktRec;
static std::vector<std::pair<Ptr<const Packet>, bool>> g_pktOrder; // ordre d'emission
static std::set<uint32_t> g_mobileNodes;
static std::vector<Vector> g_gwPos;
// Descendantes vers les noeuds mobiles : (instant, noeud, passerelle).
static std::vector<std::tuple<double, uint32_t, uint32_t>> g_downlinks;
static std::map<uint32_t, uint32_t> g_addrToNode;
// Type de la prochaine trame nouvelle d'un noeud (0 routine, 1 alerte, 2 sonde, 3 lot).
static std::map<uint32_t, int> g_nextKind;

// Trames d'alerte (pointeurs), pour les distinguer de la routine.
static std::set<Ptr<const Packet>> g_alertPkts;

// Consignes v6 : suivi par alerte. Production -> premiere reception passerelle
// (exigence de 15 min cote reseau), acquittement, alarme technique locale du
// pont quand l'alerte confirmee n'est pas acquittee (issue negative ou alerte
// abandonnee parce qu'une nouvelle la remplace).
struct AlertRec
{
  uint32_t node;
  double tGen;
  bool indoor;
  bool delivered = false;
  double tDeliv = -1.0;
  bool acked = false;
  bool alarm = false;
  bool pending = false;     // v6.2 : alarme en attente du recapitulatif
  double tAlarm = -1.0;     // instant ou l'alarme est levee
};
static std::vector<AlertRec> g_alertRecs;
static std::map<Ptr<const Packet>, size_t> g_alertIdx;

// Consignes v6 : perte en interieur courante de chaque noeud (dB), mise a jour
// par le calendrier interieur / exterieur. Absente = dehors.
static std::map<uint32_t, double> g_indoorNow;

// Maillon de propagation : retranche la perte en interieur de chaque extremite
// qui est un noeud a l'interieur (montante et descendante, liens noeud-noeud
// compris). Les passerelles ne sont jamais a l'interieur.
class IndoorLossModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::StopMntIndoorLossModel")
                            .SetParent<PropagationLossModel> ()
                            .SetGroupName ("StopMnt")
                            .AddConstructor<IndoorLossModel> ();
    return tid;
  }

private:
  static double Of (Ptr<MobilityModel> m)
  {
    Ptr<Node> n = m->GetObject<Node> ();
    if (!n)
      {
        return 0.0;
      }
    auto it = g_indoorNow.find (n->GetId ());
    return it == g_indoorNow.end () ? 0.0 : it->second;
  }
  double DoCalcRxPower (double txPowerDbm, Ptr<MobilityModel> a, Ptr<MobilityModel> b) const override
  {
    return txPowerDbm - Of (a) - Of (b);
  }
  int64_t DoAssignStreams (int64_t stream) override
  {
    return 0;
  }
};
NS_OBJECT_ENSURE_REGISTERED (IndoorLossModel);

static void
SetIndoor (uint32_t nodeId, double lossDb)
{
  g_indoorNow[nodeId] = lossDb;
}

// Indice de la passerelle la plus proche de chaque noeud (noeuds fixes).
static std::map<uint32_t, uint32_t> g_nodeNearestGw;

// Trame nouvelle -> noeud emetteur, pour attribuer une reception.
static std::map<Ptr<const Packet>, uint32_t> g_pktSender;
// Nombre de passerelles ayant recu chaque trame. La premiere reception compte
// comme livraison (deduplication, comme le serveur), les suivantes comme doublons.
static std::map<Ptr<const Packet>, uint32_t> g_pktGwCount;
// Passerelles distinctes ayant recu chaque trame (les retransmissions d'une
// trame confirmee reprennent la meme trame : elles ne font pas de diversite).
static std::map<Ptr<const Packet>, std::set<uint32_t>> g_pktGwSet;
// Instant d'emission MAC de chaque trame nouvelle, pour la latence.
static std::map<Ptr<const Packet>, Time> g_pktSendTime;
// Arrivees au serveur, doublons compris (une par passerelle qui relaie).
static uint64_t g_nsArrivals = 0;

static int
NearestGw (const Vector &p, double &dist)
{
  dist = 1e300;
  int best = 0;
  for (size_t g = 0; g < g_gwPos.size (); ++g)
    {
      double d = std::hypot (p.x - g_gwPos[g].x, p.y - g_gwPos[g].y);
      if (d < dist)
        {
          dist = d;
          best = static_cast<int> (g);
        }
    }
  return best;
}

static void
OnMacNewPacket (uint32_t nodeId, Ptr<const Packet> p)
{
  if (g_mobileNodes.count (nodeId))
    {
      Ptr<Node> node = NodeList::GetNode (nodeId);
      Vector pos = node->GetObject<MobilityModel> ()->GetPosition ();
      Ptr<EndDeviceLorawanMac> mac = DynamicCast<EndDeviceLorawanMac> (
          DynamicCast<LoraNetDevice> (node->GetDevice (0))->GetMac ());
      PktRec r;
      r.node = nodeId;
      r.t = Simulator::Now ().GetSeconds ();
      r.x = pos.x;
      r.y = pos.y;
      r.nearGw = NearestGw (pos, r.dNear);
      r.sf = mac->GetSfFromDataRate (mac->GetDataRate ());
      r.kind = g_alertPkts.count (p) ? 1 : g_nextKind[nodeId];
      auto fr = g_frameReadings.find (p);
      r.nReadings = (fr == g_frameReadings.end ()) ? 0 : static_cast<int> (fr->second.size ());
      g_pktRec[p] = r;
      g_pktOrder.emplace_back (p, true);
    }
  g_nodeStats[nodeId].newSent++;
  if (g_alertPkts.count (p))
    {
      g_nodeStats[nodeId].alertNew++;
    }
  g_pktSender[p] = nodeId;
  g_pktSendTime[p] = Simulator::Now ();
}

static void
OnPhyStartSending (Ptr<LorawanMac> mac, Ptr<const Packet> p, uint32_t nodeId)
{
  NodeStats &s = g_nodeStats[nodeId];
  s.txTotal++;
  // Temps d'antenne recalcule comme la MAC le fait avant d'emettre : SF lu dans
  // l'etiquette du paquet, autres parametres aux valeurs par defaut du module,
  // preambule lu sur la MAC, regle LDRO identique a celle du module.
  LoraTag tag;
  p->PeekPacketTag (tag);
  LoraTxParameters params;
  params.spreadingFactor = tag.GetSpreadingFactor ();
  params.lowDataRateOptimize =
      (params.spreadingFactor == 11 || params.spreadingFactor == 12) &&
      params.bandwidthHz == 125000;
  params.preambleLenSymb = mac->GetNPreambleSymbols ();
  s.airtimeS += LoraPhy::GetTimeOnAir (p->GetSize (), params).GetSeconds ();
}

static void
OnConfirmedOutcome (uint32_t nodeId, uint8_t txCount, bool ack, Time firstAttempt,
                    Ptr<Packet> p)
{
  ConfClose (p, ack);
  if (ack)
    {
      NodeStats &s = g_nodeStats[nodeId];
      s.acked++;
      if (g_alertPkts.count (p))
        {
          s.alertAcked++;
          auto ai = g_alertIdx.find (p);
          if (ai != g_alertIdx.end ())
            {
              g_alertRecs[ai->second].acked = true;
            }
          double rtt = (Simulator::Now () - firstAttempt).GetSeconds ();
          s.alertRttSumS += rtt;
          s.alertRttMaxS = std::max (s.alertRttMaxS, rtt);
        }
    }
}

static void
OnGwMacReceived (uint32_t gwIndex, Ptr<const Packet> p)
{
  auto it = g_pktSender.find (p);
  if (it == g_pktSender.end ())
    {
      return;
    }
  NodeStats &s = g_nodeStats[it->second];
  if (g_nodeNearestGw[it->second] == gwIndex)
    {
      s.rxNearest++;
    }
  uint32_t &count = g_pktGwCount[p];
  count++;
  s.gwReceptions++;
  auto pr = g_pktRec.find (p);
  if (pr != g_pktRec.end ())
    {
      pr->second.gws.insert (gwIndex);
    }
  if (count == 1)
    {
      if (pr != g_pktRec.end ())
        {
          pr->second.delivered = true;
          pr->second.lat = (Simulator::Now () - g_pktSendTime[p]).GetSeconds ();
        }
      // Mesures portees par la trame : livrees a la premiere reception.
      auto fr = g_frameReadings.find (p);
      if (fr != g_frameReadings.end ())
        {
          for (const auto &nr : fr->second)
            {
              Reading &rd = g_readings[nr.first][nr.second];
              if (!rd.delivered)
                {
                  rd.delivered = true;
                  rd.tDeliv = Simulator::Now ().GetSeconds ();
                  NodeStats &ns = g_nodeStats[nr.first];
                  ns.readingsDelivered++;
                  double l = rd.tDeliv - rd.tGen;
                  ns.readingLatSumS += l;
                  ns.readingLatMaxS = std::max (ns.readingLatMaxS, l);
                }
            }
        }
      s.received++;
      double lat = (Simulator::Now () - g_pktSendTime[p]).GetSeconds ();
      s.latencySumS += lat;
      s.latencyMaxS = std::max (s.latencyMaxS, lat);
      if (g_alertPkts.count (p))
        {
          s.alertDelivered++;
          s.alertLatUpMaxS = std::max (s.alertLatUpMaxS, lat);
          auto ai = g_alertIdx.find (p);
          if (ai != g_alertIdx.end ())
            {
              g_alertRecs[ai->second].delivered = true;
              g_alertRecs[ai->second].tDeliv = Simulator::Now ().GetSeconds ();
            }
        }
    }
  std::set<uint32_t> &gws = g_pktGwSet[p];
  if (gws.insert (gwIndex).second && gws.size () == 2)
    {
      s.multiGw++;   // deuxieme passerelle distincte : diversite effective
    }
}

static void
OnNsReceived (Ptr<const Packet> p)
{
  g_nsArrivals++;
}

// Descendante emise par une passerelle : on retrouve le noeud destinataire par
// son adresse, et on la note si ce noeud est mobile (choix de la passerelle
// pour l'acquittement).
static void
OnGwDownlink (uint32_t gwIndex, Ptr<const Packet> p)
{
  Ptr<Packet> c = p->Copy ();
  LorawanMacHeader mh;
  c->RemoveHeader (mh);
  LoraFrameHeader fh;
  fh.SetAsDownlink ();
  c->RemoveHeader (fh);
  auto it = g_addrToNode.find (fh.GetAddress ().Get ());
  if (it != g_addrToNode.end () && g_mobileNodes.count (it->second))
    {
      g_downlinks.emplace_back (Simulator::Now ().GetSeconds (), it->second, gwIndex);
    }
}

// Pointeurs globaux pour l'adaptation du SF des noeuds mobiles.
static Ptr<LoraChannel> g_channelPtr;
static NodeContainer g_gatewaysForSf;

// =============================================================================
// Application de profil patient.
//
// Une instance par noeud. Elle produit :
//   - la routine : une trame de routineSize octets toutes les routinePeriod,
//     premier envoi tire uniformement dans [0, routinePeriod] comme l'emetteur
//     periodique du module ;
//   - l'alerte critique, superposee : processus de Poisson de alertPerDay
//     alertes par jour, en mode confirme avec alertNbTrans transmissions max.
//
// Le module regle le mode confirme par appareil (FType) et le lit a chaque
// emission ; une trame nouvelle remplace toujours celle en cours (source :
// EndDeviceLorawanMac::Send et DoSend, module 0.3.7). On regle donc FType et
// nbTrans juste avant chaque envoi. Pour qu'une routine n'interrompe pas une
// alerte en attente d'acquittement, deferDuringAlert differe la routine
// jusqu'a l'issue de l'alerte (option, a valider).
// =============================================================================
class ProfileSender : public Application
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::ProfileSender")
                            .SetParent<Application> ()
                            .SetGroupName ("Lora")
                            .AddConstructor<ProfileSender> ();
    return tid;
  }

  struct Params
  {
    Time routinePeriod;
    uint32_t readingSize = 0;      // octets d'une mesure (charge)
    uint32_t micBytes = 0;         // ajoutes a chaque trame (MIC non modelise)
    bool routineConfirmed = false;
    uint8_t routineNbTrans = 1;
    double alertPerDay = 0.0;
    uint32_t alertSize = 0;        // taille passee a la MAC
    uint8_t alertNbTrans = 1;
    bool deferDuringAlert = true;
    bool alertConfirmed = true;    // false : alerte non confirmee (mode tout non confirme)
    Time confGuard;                // garde d'une routine confirmee sans issue
    bool sfOracle = false;         // SF recalcule avant chaque envoi (mobiles)
    // Store-and-forward
    bool sfw = false;
    uint32_t probeEvery = 0;       // une routine sur k est confirmee (sonde)
    uint32_t bufferMax = 0;        // mesures gardees au plus
    Time flushInterval;            // espacement des lots de vidage
    uint8_t sfwNbTrans = 1;        // transmissions max d'une sonde ou d'un lot
    std::vector<uint32_t> maxMacPayload; // par DR, table du module
    // Consignes v6, point 7 : mixte a recapitulatif quotidien. Routine sans
    // accuse ; a l'echeance, la premiere montee porte une demande de
    // recapitulatif (emule par une trame confirmee a une seule transmission :
    // la descendante qui la suit est le recapitulatif) ; le pont renvoie les
    // mesures manquantes depuis son tampon.
    bool recap = false;
    Time recapPeriod;              // echeance du serveur (24 h, variante 12 h)
    Time recapRequest;             // demande par le pont sans recapitulatif depuis (26 h)
    Time recapAlarm;               // alarme technique sans recapitulatif depuis (48 h)
    Time recapBuffer;              // profondeur du tampon (72 h)
    double recapAlarmFill = 0.9;   // alarme si le tampon est rempli a ce taux
    uint32_t recapMask = 32;       // trames couvertes par le masque du recapitulatif
    bool alarmTwoStage = false;    // v6.2 : alarme en deux temps (recapitulatif)
    Time alarmPendingMax;          // v6.2 : garde-fou de l'attente
  };

  void Configure (Ptr<ClassAEndDeviceLorawanMac> mac, Ptr<Node> node, const Params &pr)
  {
    m_mac = mac;
    m_node = node;
    m_nodeId = node->GetId ();
    m_p = pr;
    m_mac->TraceConnectWithoutContext ("ConfirmedTransmissionOutcome",
                                       MakeCallback (&ProfileSender::OnOutcome, this));
  }

private:
  void StartApplication () override
  {
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable> ();
    m_routineEvent = Simulator::Schedule (Seconds (u->GetValue (0, m_p.routinePeriod.GetSeconds ())),
                                          &ProfileSender::Routine, this);
    if (m_p.alertPerDay > 0.0)
      {
        m_expo = CreateObject<ExponentialRandomVariable> ();
        m_expo->SetAttribute ("Mean", DoubleValue (86400.0 / m_p.alertPerDay));
        m_alertEvent = Simulator::Schedule (Seconds (m_expo->GetValue ()), &ProfileSender::Alert, this);
      }
  }

  void StopApplication () override
  {
    Simulator::Cancel (m_routineEvent);
    Simulator::Cancel (m_alertEvent);
    Simulator::Cancel (m_flushEvent);
    Simulator::Cancel (m_guardEvent);
    Simulator::Cancel (m_routineGuard);
    Simulator::Cancel (m_resendEvent);
  }

  // Nouvelle mesure : on la note (instant, position) et on rend son numero.
  uint32_t NewReading ()
  {
    Vector pos = m_node->GetObject<MobilityModel> ()->GetPosition ();
    std::vector<Reading> &v = g_readings[m_nodeId];
    v.push_back (Reading{Simulator::Now ().GetSeconds (), pos.x, pos.y, false, -1.0, false});
    g_nodeStats[m_nodeId].readingsGen++;
    return static_cast<uint32_t> (v.size () - 1);
  }

  void AdaptSf ()
  {
    if (m_p.sfOracle && g_channelPtr)
      {
        LorawanMacHelper::SetSpreadingFactorsUp (NodeContainer (m_node), g_gatewaysForSf, g_channelPtr);
      }
  }

  // Envoie une trame portant les mesures donnees.
  Ptr<Packet> SendReadings (const std::vector<uint32_t> &seqs, bool confirmed, uint8_t nbTrans, int kind)
  {
    AdaptSf ();
    Ptr<Packet> p = Create<Packet> (seqs.size () * m_p.readingSize + m_p.micBytes);
    auto &fr = g_frameReadings[p];
    for (uint32_t q : seqs)
      {
        fr.emplace_back (m_nodeId, q);
      }
    m_mac->SetFType (confirmed ? LorawanMacHeader::CONFIRMED_DATA_UP
                               : LorawanMacHeader::UNCONFIRMED_DATA_UP);
    m_mac->SetMaxNumberOfTransmissions (nbTrans);
    g_nextKind[m_nodeId] = kind;
    if (confirmed)
      {
        m_pendingData = p;
        m_pendingSeqs = seqs;
        // Garde : le module peut ecraser une trame retardee sans jamais en
        // signaler l'issue. Passe ce delai, on la tient pour perdue.
        Simulator::Cancel (m_guardEvent);
        m_guardEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::DataGuard, this, p);
      }
    m_mac->Send (p);
    return p;
  }

  void DataGuard (Ptr<Packet> p)
  {
    if (m_dataPending && p == m_pendingData)
      {
        OnOutcome (0, false, Seconds (0), p);
      }
  }

  // Nombre de mesures par trame au debit courant (table du module, en-tete 8 o).
  uint32_t ReadingsPerFrame ()
  {
    uint8_t dr = m_mac->GetDataRate ();
    uint32_t maxMac = m_p.maxMacPayload.empty () ? 59 : m_p.maxMacPayload.at (dr);
    uint32_t room = (maxMac > 8 + m_p.micBytes) ? maxMac - 8 - m_p.micBytes : 0;
    return std::max<uint32_t> (1, room / std::max<uint32_t> (1, m_p.readingSize));
  }

  void Routine ()
  {
    g_nodeStats[m_nodeId].genRoutine++;
    uint32_t seq = NewReading ();
    m_routineCount++;
    m_routineEvent = Simulator::Schedule (m_p.routinePeriod, &ProfileSender::Routine, this);

    if (m_p.recap)
      {
        RecapBookkeeping (seq);
      }
    if (!m_p.sfw)
      {
        // Pas de file dans la MAC du module : une trame nouvelle ecrase celle
        // en cours. La routine attend donc l'issue de l'alerte (si differee)
        // ou de la routine confirmee precedente, comme une pile LoRaWAN reelle.
        if ((m_alertPending && m_p.deferDuringAlert) || m_routinePending || !m_waiting.empty ())
          {
            m_waiting.push_back (seq);
            return;
          }
        SendRoutine (seq);
        return;
      }

    // Store-and-forward.
    if (m_connected && m_buffer.empty () && !m_dataPending)
      {
        if (m_alertPending && m_p.deferDuringAlert)
          {
            PushBuffer (seq);
            return;
          }
        bool probe = (m_p.probeEvery > 0 && m_routineCount % m_p.probeEvery == 0);
        if (probe)
          {
            m_dataPending = true;
            SendReadings ({seq}, true, m_p.sfwNbTrans, 2);
          }
        else
          {
            SendReadings ({seq}, false, 1, 0);
          }
        return;
      }
    // Deconnecte, ou tampon non vide : la mesure va au tampon, et on tente un
    // lot confirme si aucun n'est deja en vol.
    PushBuffer (seq);
    if (!m_dataPending && !(m_alertPending && m_p.deferDuringAlert))
      {
        SendLot ();
      }
  }

  void PushBuffer (uint32_t seq)
  {
    m_buffer.push_back (seq);
    while (m_buffer.size () > m_p.bufferMax)
      {
        uint32_t old = m_buffer.front ();
        m_buffer.pop_front ();
        Reading &rd = g_readings[m_nodeId][old];
        if (!rd.delivered && !rd.dropped)
          {
            rd.dropped = true;
            g_nodeStats[m_nodeId].readingsDropped++;
          }
      }
  }

  void SendRoutine (uint32_t seq)
  {
    if (m_p.recap && WantRecap ())
      {
        // Montee qui porte la demande de recapitulatif : confirmee, une seule
        // transmission ; l'issue dit si le recapitulatif est arrive.
        Ptr<Packet> rp = SendReadings ({seq}, true, 1, 4);
        g_nodeStats[m_nodeId].recapAttempts++;
        m_routinePending = true;
        m_pendingRoutine = rp;
        m_pendingRoutineSeq = seq;
        m_recapPkt = rp;
        Simulator::Cancel (m_routineGuard);
        m_routineGuard = Simulator::Schedule (m_p.confGuard, &ProfileSender::RoutineGuard, this, rp);
        return;
      }
    Ptr<Packet> p = SendReadings ({seq}, m_p.routineConfirmed, m_p.routineNbTrans, 0);
    if (m_p.routineConfirmed)
      {
        m_routinePending = true;
        m_pendingRoutine = p;
        m_pendingRoutineSeq = seq;
        g_nodeStats[m_nodeId].confRoutineGen++;
        ConfRegister (p, m_nodeId, 0, g_readings[m_nodeId][seq].tGen);
        Simulator::Cancel (m_routineGuard);
        m_routineGuard = Simulator::Schedule (m_p.confGuard, &ProfileSender::RoutineGuard, this, p);
      }
  }

  // Envoie la routine suivante en attente, une a la fois.
  void FlushWaiting ()
  {
    if (m_waiting.empty () || m_routinePending || (m_alertPending && m_p.deferDuringAlert))
      {
        return;
      }
    uint32_t q = m_waiting.front ();
    m_waiting.pop_front ();
    SendRoutine (q);
    if (!m_p.routineConfirmed && !m_waiting.empty ())
      {
        // Non confirme : pas d'issue a attendre, on espace pour que la MAC
        // n'ecrase pas une trame retardee par le cycle de service.
        Simulator::Cancel (m_flushEvent);
        m_flushEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::FlushWaiting, this);
      }
  }

  void RoutineGuard (Ptr<Packet> p)
  {
    if (m_routinePending && p == m_pendingRoutine)
      {
        g_guardFires++;
        ConfClose (p, false);
        m_routinePending = false;
        FlushWaiting ();
      }
  }

  void SendLot ()
  {
    if (m_buffer.empty ())
      {
        return;
      }
    AdaptSf ();
    uint32_t k = std::min<uint32_t> (ReadingsPerFrame (), m_buffer.size ());
    std::vector<uint32_t> seqs (m_buffer.begin (), m_buffer.begin () + k);
    m_dataPending = true;
    SendReadings (seqs, true, m_p.sfwNbTrans, 3);
  }

  void Alert ()
  {
    g_nodeStats[m_nodeId].genAlert++;
    // L'alerte va remplacer toute trame en cours dans la MAC : si une sonde ou
    // un lot attendait son acquittement, on le declare interrompu (ses mesures
    // restent au tampon) au lieu d'attendre une issue qui ne viendra pas.
    if (m_p.sfw && m_dataPending)
      {
        OnOutcome (0, false, Seconds (0), m_pendingData);
      }
    // Une routine confirmee en vol serait ecrasee par l'alerte : on la remet
    // en tete de file, elle repartira apres l'alerte (delai compte depuis sa
    // production).
    if (m_routinePending)
      {
        auto it = g_confIndex.find (m_pendingRoutine);
        if (it != g_confIndex.end ())
          {
            g_confFrames[it->second].done = true;   // entree abandonnee, non comptee
            g_confFrames[it->second].kind = -1;
          }
        g_nodeStats[m_nodeId].confRoutineGen--;
        Simulator::Cancel (m_routineGuard);
        m_routinePending = false;
        m_waiting.push_front (m_pendingRoutineSeq);
        g_requeued++;
      }
    // Une alerte confirmee encore en vol est abandonnee (la MAC va la
    // remplacer) : le pont le sait et leve l'alarme technique locale.
    if (m_alertPending && m_p.alertConfirmed)
      {
        RaiseAlertAlarm (m_pendingAlert);
        m_alertPending = false;
      }
    AdaptSf ();
    Ptr<Packet> p = Create<Packet> (m_p.alertSize);
    g_alertPkts.insert (p);
    {
      auto it = g_indoorNow.find (m_nodeId);
      AlertRec ar;
      ar.node = m_nodeId;
      ar.tGen = Simulator::Now ().GetSeconds ();
      ar.indoor = (it != g_indoorNow.end () && it->second > 0.0);
      g_alertIdx[p] = g_alertRecs.size ();
      g_alertRecs.push_back (ar);
    }
    if (m_p.alertConfirmed)
      {
        m_pendingAlert = p;
        m_alertPending = true;
        ConfRegister (p, m_nodeId, 1, Simulator::Now ().GetSeconds ());
        m_mac->SetFType (LorawanMacHeader::CONFIRMED_DATA_UP);
        m_mac->SetMaxNumberOfTransmissions (m_p.alertNbTrans);
      }
    else
      {
        m_mac->SetFType (LorawanMacHeader::UNCONFIRMED_DATA_UP);
        m_mac->SetMaxNumberOfTransmissions (1);
      }
    m_mac->Send (p);
    if (!m_p.alertConfirmed && !m_p.sfw && !m_waiting.empty ())
      {
        Simulator::Cancel (m_flushEvent);
        m_flushEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::FlushWaiting, this);
      }
    m_alertEvent = Simulator::Schedule (Seconds (m_expo->GetValue ()), &ProfileSender::Alert, this);
  }

  void OnOutcome (uint8_t txCount, bool ack, Time firstAttempt, Ptr<Packet> p)
  {
    if (m_alertPending && p == m_pendingAlert)
      {
        m_alertPending = false;
        if (!ack)
          {
            RaiseAlertAlarm (p);
          }
        if (!m_p.sfw)
          {
            FlushWaiting ();
          }
        if (m_p.sfw && !m_dataPending && !m_buffer.empty ())
          {
            SendLot ();
          }
        return;
      }
    if (!m_p.sfw && m_routinePending && p == m_pendingRoutine)
      {
        if (m_p.recap && p == m_recapPkt)
          {
            OnRecapOutcome (ack, p);
          }
        m_routinePending = false;
        Simulator::Cancel (m_routineGuard);
        FlushWaiting ();
        return;
      }
    if (m_p.sfw && m_dataPending && p == m_pendingData)
      {
        m_dataPending = false;
        Simulator::Cancel (m_guardEvent);
        m_connected = ack;
        if (ack)
          {
            // Les mesures du lot sont acquittees : on les retire du tampon.
            std::set<uint32_t> done (m_pendingSeqs.begin (), m_pendingSeqs.end ());
            std::deque<uint32_t> rest;
            for (uint32_t q : m_buffer)
              {
                if (!done.count (q))
                  {
                    rest.push_back (q);
                  }
              }
            m_buffer.swap (rest);
            if (!m_buffer.empty ())
              {
                m_flushEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::SendLot, this);
              }
          }
        else
          {
            // Sonde ou lot non acquitte : les mesures restent (ou vont) au tampon.
            for (uint32_t q : m_pendingSeqs)
              {
                if (std::find (m_buffer.begin (), m_buffer.end (), q) == m_buffer.end () &&
                    !g_readings[m_nodeId][q].delivered)
                  {
                    PushBuffer (q);
                  }
              }
          }
      }
  }

  void RaiseAlertAlarm (Ptr<Packet> p)
  {
    auto ai = g_alertIdx.find (p);
    if (ai == g_alertIdx.end () || g_alertRecs[ai->second].alarm || g_alertRecs[ai->second].pending)
      {
        return;
      }
    AlertRec &ar = g_alertRecs[ai->second];
    if (m_p.recap && m_p.alarmTwoStage)
      {
        // Complement v6.2 : alarme en deux temps. L'accuse manque : l'alarme
        // passe en attente et le pont demande un recapitulatif a sa prochaine
        // montee ; le recapitulatif dira si l'alerte est arrivee.
        ar.pending = true;
        m_pendingAlerts.push_back (ai->second);
        m_recapUrgent = true;
        Simulator::Schedule (m_p.alarmPendingMax, &ProfileSender::PendingTimeout, this, ai->second);
        return;
      }
    ar.alarm = true;
    ar.tAlarm = Simulator::Now ().GetSeconds ();
  }

  // Garde-fou : sans recapitulatif dans le delai, l'alarme est levee.
  void PendingTimeout (size_t idx)
  {
    AlertRec &ar = g_alertRecs[idx];
    if (ar.pending)
      {
        ar.pending = false;
        ar.alarm = true;
        ar.tAlarm = Simulator::Now ().GetSeconds ();
      }
  }

  // Le recapitulatif recu tranche les alarmes en attente : alerte arrivee au
  // serveur -> annulee ; sinon -> alarme levee.
  void ResolvePending ()
  {
    for (size_t idx : m_pendingAlerts)
      {
        AlertRec &ar = g_alertRecs[idx];
        if (!ar.pending)
          {
            continue;
          }
        ar.pending = false;
        if (!ar.delivered)
          {
            ar.alarm = true;
            ar.tAlarm = Simulator::Now ().GetSeconds ();
          }
      }
    m_pendingAlerts.clear ();
    m_recapUrgent = false;
  }

  // Le pont garde chaque mesure de routine dans son tampon de recapitulatif ;
  // celles plus vieilles que la profondeur du tampon en sortent (perdues si
  // jamais livrees). Alarme technique : pas de recapitulatif depuis
  // recapAlarm, ou tampon rempli au-dela de recapAlarmFill.
  void RecapBookkeeping (uint32_t seq)
  {
    double now = Simulator::Now ().GetSeconds ();
    m_recapBuf.push_back (seq);
    std::vector<Reading> &v = g_readings[m_nodeId];
    while (!m_recapBuf.empty () && now - v[m_recapBuf.front ()].tGen > m_p.recapBuffer.GetSeconds ())
      {
        Reading &rd = v[m_recapBuf.front ()];
        if (!rd.delivered && !rd.dropped)
          {
            rd.dropped = true;
            g_nodeStats[m_nodeId].readingsDropped++;
          }
        m_recapBuf.pop_front ();
      }
    size_t cap = static_cast<size_t> (m_p.recapBuffer.GetSeconds () / m_p.routinePeriod.GetSeconds ());
    size_t pending = 0;
    for (uint32_t q : m_recapBuf)
      {
        pending += v[q].delivered ? 0 : 1;
      }
    bool alarm = (now - m_lastRecapRx >= m_p.recapAlarm.GetSeconds ()) ||
                 (cap > 0 && pending >= m_p.recapAlarmFill * cap);
    if (alarm && !m_techAlarmOn)
      {
        g_nodeStats[m_nodeId].techAlarms++;
      }
    m_techAlarmOn = alarm;
  }

  bool WantRecap () const
  {
    double now = Simulator::Now ().GetSeconds ();
    return m_recapUrgent || (now - m_lastRecapTry >= m_p.recapPeriod.GetSeconds ()) ||
           (now - m_lastRecapRx >= m_p.recapRequest.GetSeconds ());
  }

  void OnRecapOutcome (bool ack, Ptr<Packet> p)
  {
    double now = Simulator::Now ().GetSeconds ();
    auto gc = g_pktGwCount.find (p);
    if (gc != g_pktGwCount.end () && gc->second > 0)
      {
        m_lastRecapTry = now;   // le serveur a recu la montee : il a tente le recapitulatif
      }
    if (!ack)
      {
        return;
      }
    g_nodeStats[m_nodeId].recapOk++;
    m_lastRecapRx = now;
    ResolvePending ();
    m_lastRecapTry = now;
    m_techAlarmOn = false;
    // Masque du recapitulatif : les recapMask dernieres trames de routine.
    std::vector<Reading> &v = g_readings[m_nodeId];
    std::deque<uint32_t> keep;
    size_t start = m_recapBuf.size () > m_p.recapMask ? m_recapBuf.size () - m_p.recapMask : 0;
    for (size_t i = 0; i < m_recapBuf.size (); ++i)
      {
        uint32_t q = m_recapBuf[i];
        if (v[q].delivered)
          {
            continue;
          }
        keep.push_back (q);
        if (i >= start)
          {
            m_resend.push_back (q);
          }
      }
    m_recapBuf.swap (keep);
    if (!m_resend.empty ())
      {
        Simulator::Cancel (m_resendEvent);
        m_resendEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::ResendNext, this);
      }
  }

  // Renvoi des mesures manquantes, sans accuse, en lots espaces.
  void ResendNext ()
  {
    if (m_routinePending || m_alertPending || !m_waiting.empty ())
      {
        m_resendEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::ResendNext, this);
        return;
      }
    std::vector<Reading> &v = g_readings[m_nodeId];
    while (!m_resend.empty () && v[m_resend.front ()].delivered)
      {
        m_resend.pop_front ();
      }
    if (m_resend.empty ())
      {
        return;
      }
    uint32_t k = std::min<uint32_t> (ReadingsPerFrame (), m_resend.size ());
    std::vector<uint32_t> seqs (m_resend.begin (), m_resend.begin () + k);
    m_resend.erase (m_resend.begin (), m_resend.begin () + k);
    g_nodeStats[m_nodeId].resent += k;
    SendReadings (seqs, false, 1, 5);
    if (!m_resend.empty ())
      {
        m_resendEvent = Simulator::Schedule (m_p.flushInterval, &ProfileSender::ResendNext, this);
      }
  }

  Ptr<ClassAEndDeviceLorawanMac> m_mac;
  Ptr<Node> m_node;
  uint32_t m_nodeId = 0;
  Params m_p;
  // Recapitulatif quotidien (consignes v6).
  std::deque<uint32_t> m_recapBuf;
  std::deque<uint32_t> m_resend;
  Ptr<Packet> m_recapPkt;
  double m_lastRecapRx = 0.0;
  double m_lastRecapTry = 0.0;
  bool m_techAlarmOn = false;
  EventId m_resendEvent;
  std::vector<size_t> m_pendingAlerts;
  bool m_recapUrgent = false;
  bool m_alertPending = false;
  Ptr<Packet> m_pendingAlert;
  bool m_routinePending = false;
  Ptr<Packet> m_pendingRoutine;
  uint32_t m_pendingRoutineSeq = 0;
  EventId m_routineGuard;
  std::deque<uint32_t> m_waiting;
  uint32_t m_routineCount = 0;
  bool m_connected = true;
  bool m_dataPending = false;
  Ptr<Packet> m_pendingData;
  std::vector<uint32_t> m_pendingSeqs;
  std::deque<uint32_t> m_buffer;
  Ptr<ExponentialRandomVariable> m_expo;
  EventId m_routineEvent;
  EventId m_alertEvent;
  EventId m_flushEvent;
  EventId m_guardEvent;
};

NS_OBJECT_ENSURE_REGISTERED (ProfileSender);

// Champs ajoutes en fin de ligne NODE (consignes v6) :
//   readingsEligible;readingsOk72h;alertsCounted;alertsOk15;alarms;falseAlarms;
//   unconfirmedNoAlarm;alertsIndoor;alertsIndoorOk15;recapAttempts;recapOk;
//   techAlarms;resent;alertsOk5 (v6.1 : livrees en 5 min, a titre d'information);
//   trueAlarms;detectSum_s;detectMax_s (v6.2 : alarmes sur alertes non livrees, delai production -> alarme)
// Mesures evaluees : produites au plus tard evalExcludeLastS avant la fin ;
// livrees en 72 h au plus. Alertes comptees : produites au moins 15 min avant
// la fin ; livrees en 15 min au plus (production -> premiere reception).
static std::string
V6Fields (uint32_t id, double simT, double excl)
{
  uint32_t elig = 0, ok72 = 0;
  auto rv = g_readings.find (id);
  if (rv != g_readings.end ())
    {
      for (const Reading &r : rv->second)
        {
          if (r.tGen > simT - excl)
            {
              continue;
            }
          elig++;
          if (r.delivered && r.tDeliv - r.tGen <= 72.0 * 3600.0)
            {
              ok72++;
            }
        }
    }
  uint32_t na = 0, ok15 = 0, al = 0, fal = 0, unc = 0, nin = 0, okin = 0, ok5 = 0, vrais = 0;
  double detSum = 0.0, detMax = 0.0;
  for (const AlertRec &a : g_alertRecs)
    {
      if (a.node != id || a.tGen > simT - 900.0)
        {
          continue;
        }
      na++;
      bool ok = a.delivered && a.tDeliv - a.tGen <= 900.0;
      ok15 += ok;
      ok5 += (a.delivered && a.tDeliv - a.tGen <= 300.0);
      if (a.alarm && !a.delivered && a.tAlarm >= 0)
        {
          vrais++;
          detSum += a.tAlarm - a.tGen;
          detMax = std::max (detMax, a.tAlarm - a.tGen);
        }
      al += a.alarm;
      fal += (a.alarm && a.delivered);
      unc += (!a.acked && !a.alarm);
      if (a.indoor)
        {
          nin++;
          okin += ok;
        }
    }
  const NodeStats &s = g_nodeStats[id];
  std::ostringstream o;
  o << elig << ";" << ok72 << ";" << na << ";" << ok15 << ";" << al << ";" << fal << ";" << unc << ";"
    << nin << ";" << okin << ";" << s.recapAttempts << ";" << s.recapOk << ";" << s.techAlarms << ";"
    << s.resent << ";" << ok5 << ";" << vrais << ";" << detSum << ";" << detMax;
  return o.str ();
}

int
main (int argc, char *argv[])
{
  // ---------------------------------------------------------------------------
  // 1. Parametres, tous surchargeables en ligne de commande.
  // ---------------------------------------------------------------------------
  uint32_t nDevices = 100;
  double   radiusMeters = 4000.0;
  double   pathLossExp = 3.3;
  double   refLossDb = 31.2;       // perte a la distance de reference (defaut seulement, vient du config)
  double   refDistM = 1.0;         // distance de reference d0 en metres
  double   excessLossDb = 0.0;     // perte constante en exces (vegetation P.833), 0 = aucune
  std::string gwPositions = "0,0"; // passerelles : "x1,y1;x2,y2;..." en metres
  std::string profiles = "";       // profils : "periode_s:octets:nb_noeuds;..." (vide = emetteur historique)
  std::string alertProfiles = "";  // profils concernes par l'alerte : "1,0,1,..." (vide = tous)
  double   alertPerDay = 0.0;      // alertes par jour et par patient concerne (0 = aucune)
  uint32_t alertSize = 0;          // taille de la trame d'alerte passee a la MAC
  uint32_t alertNbTrans = 8;       // transmissions max d'une alerte confirmee
  bool     deferDuringAlert = true; // differer la routine pendant une alerte en attente
  bool     alertConfirmed = true;  // alerte confirmee (false en mode tout non confirme)
  double   confGuardS = 7200.0;    // garde d'une routine confirmee sans issue, s
  // Vegetation dependante de la distance (0 = aucune)
  double   gwGainDb = 0.0;
  bool     rx1Check = false;       // serveur : RX2 si le bilan prevu en RX1 ne porte pas
  double   rx1MarginDb = 0.0;      // marge exigee en RX1
  double   rx1DelayS = 1.0;        // delai RX1 du noeud (s) ; RX2 = RX1 + 1 s (consignes v4, point 13)
  double   backhaulDelayMs = 2.0;  // latence aller de la remontee passerelle vers serveur (ms)
  double   rx2PowerDbm = 27.0;     // puissance passerelle dans la sous-bande RX2 869,4-869,65 MHz (point 10)
  // Consignes v6.
  std::string gwSens = "";         // sensibilite passerelle SF7..SF12 (dBm), vide = module (SX1301)
  double   gwSensOffsetDb = 0.0;   // decalage ajoute a toutes les sensibilites passerelle
  double   indoorLossDb = 0.0;     // perte en interieur quand le pont est dedans (dB)
  double   indoorFraction = 0.0;   // part du temps a l'interieur (1 = toujours)
  bool     bhModel = false;        // remontee realiste (module, NetworkScheduler)
  double   bhMedianMs = 20.0, bhSigma = 0.5, bhSpikeProb = 0.0, bhSpikeMinS = 1.0, bhSpikeMaxS = 6.0;
  double   bhLossProb = 0.0, bhRtoMs = 200.0, dedupMs = 200.0, tooLateMs = 42.5;
  bool     recap = false;          // mixte a recapitulatif quotidien
  double   recapPeriodH = 24.0, recapRequestH = 26.0, recapAlarmH = 48.0, recapBufferH = 72.0;
  double   evalExcludeLastS = 0.0;
  bool     alarmTwoStage = false;  // v6.2 : alarme en deux temps
  double   alarmPendingMaxH = 6.0; // v6.2 : garde-fou (h) // mesures produites dans ce delai avant la fin : non evaluees (72 h)
  double   vegAmDb = 0.0;
  double   vegCoef = 0.2;
  double   vegFExp = 0.3;
  double   vegDExp = 0.6;
  double   freqMHz = 868.0;
  // Energie radio (modele du module, LoraRadioEnergyModel)
  bool     energy = false;
  double   enVoltage = 3.3;
  double   enSleepA = 0.1e-6;
  double   enStandbyA = 1.4e-3;
  double   enRxA = 10.8e-3;
  double   enTxEta = 0.452750;
  double   enTxBaseA = 0.014646;
  bool     adr = false;            // ADR du module (serveur + noeuds). Desactive : SF fixe par bilan de liaison
  double   shadowCorrDist = 0.0;   // distance de decorrelation de l'ombrage, m (Gudmundson)
  double   shadowSiteCorr = 0.0;   // correlation de l'ombrage entre sites (3GPP 0,5)
  bool     splitChannel = false;   // canaux separes montant (passerelles) / descendant (noeuds)
  // Patients mobiles, ajoutes aux nDevices noeuds fixes.
  uint32_t mobileCount = 0;        // nombre de patients mobiles
  std::string mobModel = "trajet"; // trajet (points de passage, vitesse constante) ou aleatoire (RandomWaypoint)
  std::string mobPath = "";        // trajet : "x1,y1;x2,y2;..." en m
  double   mobSpeed = 1.0;         // m/s
  double   mobPause = 0.0;         // pause a chaque point, s
  double   mobStart = 0.0;         // depart du premier mobile, s
  double   mobStagger = 0.0;       // decalage de depart entre mobiles, s
  std::string mobBounds = "";      // aleatoire : "xmin,xmax,ymin,ymax"
  std::string mobileProfile = "";  // "periode_s:octets_mesure" (vide = profil 0)
  bool     mobileAlert = true;     // les mobiles emettent aussi des alertes
  std::string mobileSf = "fixe";   // fixe (SF au depart), sf12, oracle (recalcul avant envoi)
  // Store-and-forward (tous les noeuds a profil si actif)
  bool     sfw = false;
  uint32_t sfwProbeEvery = 4;
  uint32_t sfwBuffer = 96;
  double   sfwFlush = 300.0;
  uint32_t sfwNbTrans = 2;
  std::string maxMacPayload = "59,59,59,123,230,230";
  uint32_t micBytes = 4;
  double   appPeriodSeconds = 8640.0;
  uint32_t packetSize = 24;        // charge + MIC, le module ajoute 9 octets
  double   simTimeSeconds = 172800.0;
  double   gwHeightM = 15.0;
  double   edHeightM = 1.2;
  uint32_t runNumber = 1;
  double   shadowingSigma = 8.0;   // ici l'ombrage est actif par defaut
  bool     confirmed = false;      // mode confirme (acquittement) desactive par defaut
  uint32_t nbTrans = 8;            // nb max de transmissions d'une trame confirmee
  std::string zoneLabel = "na";
  std::string expLabel = "capacite";
  bool     nodeTrace = true;       // une ligne NODE par noeud en sortie
  double   horizonCoefKm = 0.0;    // borne d'horizon desactivee par defaut (horizon applique en analyse)
  double   horizonLossDb = 300.0;  // perte sentinelle au-dela de l'horizon
  std::string placement = "disque"; // disque : uniforme en surface ; distance : uniforme en distance

  CommandLine cmd (__FILE__);
  cmd.AddValue ("nDevices", "Nombre de noeuds", nDevices);
  cmd.AddValue ("radius", "Rayon de la cellule en metres", radiusMeters);
  cmd.AddValue ("pathLossExp", "Exposant de perte", pathLossExp);
  cmd.AddValue ("refLoss", "Perte a la distance de reference, en dB", refLossDb);
  cmd.AddValue ("refDist", "Distance de reference d0, en metres", refDistM);
  cmd.AddValue ("excessLossDb", "Perte constante en exces (vegetation), en dB", excessLossDb);
  cmd.AddValue ("gwPositions", "Positions des passerelles x1,y1;x2,y2 en metres", gwPositions);
  cmd.AddValue ("profiles", "Profils periode_s:octets:nb_noeuds;... (vide = emetteur historique)", profiles);
  cmd.AddValue ("alertProfiles", "Profils concernes par l'alerte, 1,0,... (vide = tous)", alertProfiles);
  cmd.AddValue ("alertPerDay", "Alertes par jour et par patient concerne", alertPerDay);
  cmd.AddValue ("alertSize", "Taille de la trame d'alerte passee a la MAC", alertSize);
  cmd.AddValue ("alertNbTrans", "Transmissions max d'une alerte confirmee", alertNbTrans);
  cmd.AddValue ("deferDuringAlert", "Differer la routine pendant une alerte (0/1)", deferDuringAlert);
  cmd.AddValue ("alertConfirmed", "Alerte confirmee (0/1)", alertConfirmed);
  cmd.AddValue ("confGuard", "Garde d'une routine confirmee sans issue (s)", confGuardS);
  cmd.AddValue ("rx1Check", "Serveur : accuse en RX2 si RX1 ne porte pas (0/1)", rx1Check);
  cmd.AddValue ("rx1MarginDb", "Marge exigee pour repondre en RX1 (dB)", rx1MarginDb);
  cmd.AddValue ("rx1Delay", "Delai d'ouverture de RX1 en s (RX2 = RX1 + 1 s)", rx1DelayS);
  cmd.AddValue ("backhaulDelayMs", "Latence aller passerelle vers serveur (ms)", backhaulDelayMs);
  cmd.AddValue ("rx2PowerDbm", "Puissance passerelle en RX2, sous-bande 869,4-869,65 MHz (dBm)", rx2PowerDbm);
  cmd.AddValue ("gwSens", "Sensibilite passerelle SF7..SF12 en dBm, separees par des virgules", gwSens);
  cmd.AddValue ("gwSensOffsetDb", "Decalage de la sensibilite passerelle (dB)", gwSensOffsetDb);
  cmd.AddValue ("indoorLossDb", "Perte en interieur du pont (dB)", indoorLossDb);
  cmd.AddValue ("indoorFraction", "Part du temps a l'interieur (0 a 1)", indoorFraction);
  cmd.AddValue ("bhModel", "Remontee realiste (0/1)", bhModel);
  cmd.AddValue ("bhMedianMs", "Remontee : mediane de la latence aller simple (ms)", bhMedianMs);
  cmd.AddValue ("bhSigma", "Remontee : ecart-type du log de la latence", bhSigma);
  cmd.AddValue ("bhSpikeProb", "Remontee : probabilite d'un pic", bhSpikeProb);
  cmd.AddValue ("bhSpikeMinS", "Remontee : pic, borne basse (s)", bhSpikeMinS);
  cmd.AddValue ("bhSpikeMaxS", "Remontee : pic, borne haute (s)", bhSpikeMaxS);
  cmd.AddValue ("bhLossProb", "Remontee : perte TCP par trajet", bhLossProb);
  cmd.AddValue ("bhRtoMs", "Remontee : RTO minimal (ms)", bhRtoMs);
  cmd.AddValue ("dedupMs", "Serveur : attente de deduplication (ms)", dedupMs);
  cmd.AddValue ("tooLateMs", "Passerelle : marge TOO_LATE (ms)", tooLateMs);
  cmd.AddValue ("recap", "Mixte a recapitulatif quotidien (0/1)", recap);
  cmd.AddValue ("recapPeriodH", "Echeance du recapitulatif (h)", recapPeriodH);
  cmd.AddValue ("recapRequestH", "Demande du pont sans recapitulatif depuis (h)", recapRequestH);
  cmd.AddValue ("recapAlarmH", "Alarme technique sans recapitulatif depuis (h)", recapAlarmH);
  cmd.AddValue ("recapBufferH", "Profondeur du tampon du pont (h)", recapBufferH);
  cmd.AddValue ("alarmTwoStage", "Alarme en deux temps, mode recapitulatif (0/1)", alarmTwoStage);
  cmd.AddValue ("alarmPendingMaxH", "Garde-fou de l'alarme en attente (h)", alarmPendingMaxH);
  cmd.AddValue ("evalExcludeLastS", "Mesures des dernieres secondes non evaluees (72 h)", evalExcludeLastS);
  cmd.AddValue ("gwGainDb", "Gain d'antenne de la passerelle en reception (dBi)", gwGainDb);
  cmd.AddValue ("vegAm", "Saturation de la vegetation Am (dB, 0 = aucune)", vegAmDb);
  cmd.AddValue ("vegCoef", "Coefficient de croissance de la vegetation (dB)", vegCoef);
  cmd.AddValue ("vegFExp", "Exposant de frequence de la croissance", vegFExp);
  cmd.AddValue ("vegDExp", "Exposant de distance de la croissance", vegDExp);
  cmd.AddValue ("freqMHz", "Frequence porteuse (MHz), pour la vegetation", freqMHz);
  cmd.AddValue ("energy", "Mesurer l'energie radio des noeuds (0/1)", energy);
  cmd.AddValue ("enVoltage", "Tension d'alimentation (V)", enVoltage);
  cmd.AddValue ("enSleepA", "Courant en sommeil (A)", enSleepA);
  cmd.AddValue ("enStandbyA", "Courant en attente (A)", enStandbyA);
  cmd.AddValue ("enRxA", "Courant en reception (A)", enRxA);
  cmd.AddValue ("enTxEta", "Rendement de l'amplificateur (modele lineaire du module)", enTxEta);
  cmd.AddValue ("enTxBaseA", "Courant d'emission de base a 0 W (A)", enTxBaseA);
  cmd.AddValue ("adr", "ADR du module, serveur et noeuds (0/1). Actif par defaut dans le module.", adr);
  cmd.AddValue ("shadowCorrDist", "Distance de decorrelation de l'ombrage en m (0 = aucune)", shadowCorrDist);
  cmd.AddValue ("shadowSiteCorr", "Correlation de l'ombrage entre sites (0 a 1)", shadowSiteCorr);
  cmd.AddValue ("splitChannel", "Canaux separes : montantes vers passerelles seules, descendantes vers noeuds seuls (0/1)", splitChannel);
  cmd.AddValue ("mobileCount", "Patients mobiles ajoutes aux noeuds fixes", mobileCount);
  cmd.AddValue ("mobModel", "trajet ou aleatoire", mobModel);
  cmd.AddValue ("mobPath", "Points de passage x1,y1;x2,y2;... (m)", mobPath);
  cmd.AddValue ("mobSpeed", "Vitesse des mobiles (m/s)", mobSpeed);
  cmd.AddValue ("mobPause", "Pause a chaque point de passage (s)", mobPause);
  cmd.AddValue ("mobStart", "Instant de depart du premier mobile (s)", mobStart);
  cmd.AddValue ("mobStagger", "Decalage de depart entre mobiles (s)", mobStagger);
  cmd.AddValue ("mobBounds", "Zone de la marche aleatoire xmin,xmax,ymin,ymax (m)", mobBounds);
  cmd.AddValue ("mobileProfile", "Profil des mobiles periode_s:octets_mesure", mobileProfile);
  cmd.AddValue ("mobileAlert", "Les mobiles emettent des alertes (0/1)", mobileAlert);
  cmd.AddValue ("mobileSf", "SF des mobiles : fixe, sf12 ou oracle", mobileSf);
  cmd.AddValue ("sfw", "Store-and-forward actif (0/1)", sfw);
  cmd.AddValue ("sfwProbeEvery", "Une routine sur k est une sonde confirmee", sfwProbeEvery);
  cmd.AddValue ("sfwBuffer", "Taille du tampon en mesures", sfwBuffer);
  cmd.AddValue ("sfwFlush", "Espacement des lots de vidage (s)", sfwFlush);
  cmd.AddValue ("sfwNbTrans", "Transmissions max d'une sonde ou d'un lot", sfwNbTrans);
  cmd.AddValue ("maxMacPayload", "Charge MAC max par DR, table du module", maxMacPayload);
  cmd.AddValue ("micBytes", "Octets de MIC ajoutes a chaque trame (non modelise par le module)", micBytes);
  cmd.AddValue ("appPeriod", "Periode d'emission en secondes", appPeriodSeconds);
  cmd.AddValue ("pktSize", "Taille de la charge physique en octets", packetSize);
  cmd.AddValue ("simTime", "Duree simulee en secondes", simTimeSeconds);
  cmd.AddValue ("gwHeight", "Hauteur antenne passerelle en metres", gwHeightM);
  cmd.AddValue ("edHeight", "Hauteur antenne noeud en metres", edHeightM);
  cmd.AddValue ("runNumber", "Numero de run (graine)", runNumber);
  cmd.AddValue ("shadowingSigma", "Ecart-type d'ombrage en dB (0 = desactive)", shadowingSigma);
  cmd.AddValue ("confirmed", "Mode confirme avec acquittement (0 = non, 1 = oui)", confirmed);
  cmd.AddValue ("nbTrans", "Nb max de transmissions d'une trame confirmee", nbTrans);
  cmd.AddValue ("zoneLabel", "Etiquette de zone, recopiee en sortie", zoneLabel);
  cmd.AddValue ("expLabel", "Etiquette d'experience, recopiee en sortie", expLabel);
  cmd.AddValue ("nodeTrace", "Emettre une ligne NODE par noeud (0 = non, 1 = oui)", nodeTrace);
  cmd.AddValue ("horizonCoefKm", "Coefficient d'horizon radio en km (0 = desactive)", horizonCoefKm);
  cmd.AddValue ("horizonLossDb", "Perte ajoutee au-dela de l'horizon, en dB", horizonLossDb);
  cmd.AddValue ("placement", "Placement des noeuds : disque ou distance", placement);
  cmd.Parse (argc, argv);

  // Choix de la fenetre d'accuse (option ajoutee localement au module, voir
  // network-scheduler.cc) : la puissance d'emission en RX1 est celle de la
  // sous-bande 868,0-868,6 MHz du module (14 dBm).
  Config::SetDefault ("ns3::NetworkScheduler::Rx1BudgetCheck", BooleanValue (rx1Check));
  Config::SetDefault ("ns3::NetworkScheduler::GwRxGainDb", DoubleValue (gwGainDb));
  Config::SetDefault ("ns3::NetworkScheduler::Rx1MarginDb", DoubleValue (rx1MarginDb));
  // Delais des fenetres (ajout local au module, voir patch_module_lorawan).
  // Le serveur du module repond rx1Delay apres avoir recu la trame ; la
  // reponse atteint la passerelle 2 x latence apres la fin de la montante.
  // Un serveur reel anticipe cette latence (horodatage du packet forwarder) :
  // on retranche donc l'aller-retour de remontee au-dela de la reference de
  // 2 ms, ce qui laisse la reponse arriver comme dans le cas de base. Si
  // l'aller-retour depasse le delai RX1, RX1 est manque, comme en vrai.
  {
    double antic = rx1DelayS - 2.0 * (backhaulDelayMs - 2.0) / 1000.0;
    if (antic <= 0.0)
      {
        NS_FATAL_ERROR ("Remontee trop lente pour le delai RX1 : 2 x " << backhaulDelayMs
                        << " ms >= " << rx1DelayS << " s");
      }
    Config::SetDefault ("ns3::NetworkScheduler::Rx1Delay", TimeValue (Seconds (antic)));
    Config::SetDefault ("ns3::ClassAEndDeviceLorawanMac::ReceiveDelay1", TimeValue (Seconds (rx1DelayS)));
    Config::SetDefault ("ns3::ClassAEndDeviceLorawanMac::ReceiveDelay2", TimeValue (Seconds (rx1DelayS + 1.0)));
  }
  // Consignes v6, point 3 : remontee realiste (ajout local au module).
  Config::SetDefault ("ns3::NetworkScheduler::BackhaulModel", BooleanValue (bhModel));
  Config::SetDefault ("ns3::NetworkScheduler::BhMedianMs", DoubleValue (bhMedianMs));
  Config::SetDefault ("ns3::NetworkScheduler::BhSigma", DoubleValue (bhSigma));
  Config::SetDefault ("ns3::NetworkScheduler::BhSpikeProb", DoubleValue (bhSpikeProb));
  Config::SetDefault ("ns3::NetworkScheduler::BhSpikeMinS", DoubleValue (bhSpikeMinS));
  Config::SetDefault ("ns3::NetworkScheduler::BhSpikeMaxS", DoubleValue (bhSpikeMaxS));
  Config::SetDefault ("ns3::NetworkScheduler::BhLossProb", DoubleValue (bhLossProb));
  Config::SetDefault ("ns3::NetworkScheduler::BhRtoMs", DoubleValue (bhRtoMs));
  Config::SetDefault ("ns3::NetworkScheduler::DedupMs", DoubleValue (dedupMs));
  Config::SetDefault ("ns3::NetworkScheduler::TooLateMs", DoubleValue (tooLateMs));
  // Consignes v6, point 1 : sensibilite de la passerelle (SX1302 + SX1250).
  if (!gwSens.empty ())
    {
      std::istringstream ss (gwSens);
      std::string tok;
      int k = 0;
      while (std::getline (ss, tok, ',') && k < 6)
        {
          GatewayLoraPhy::SENSITIVITY[k++] = std::stod (tok);
        }
      if (k != 6)
        {
          NS_FATAL_ERROR ("gwSens attend 6 valeurs, SF7 a SF12 : " << gwSens);
        }
    }
  for (int k = 0; k < 6; ++k)
    {
      GatewayLoraPhy::SENSITIVITY[k] += gwSensOffsetDb;
    }
  if (placement != "disque" && placement != "distance")
    {
      NS_FATAL_ERROR ("placement doit valoir disque ou distance, recu : " << placement);
    }
  // Lecture des positions de passerelles.
  std::vector<Vector> gwPosList;
  {
    std::istringstream all (gwPositions);
    std::string item;
    while (std::getline (all, item, ';'))
      {
        double x, y;
        char comma;
        std::istringstream one (item);
        if (!(one >> x >> comma >> y) || comma != ',')
          {
            NS_FATAL_ERROR ("gwPositions mal forme : " << gwPositions);
          }
        gwPosList.push_back (Vector (x, y, gwHeightM));
      }
    if (gwPosList.empty ())
      {
        NS_FATAL_ERROR ("gwPositions vide");
      }
  }
  std::vector<uint32_t> maxMacList;
  {
    std::istringstream all (maxMacPayload);
    std::string f;
    while (std::getline (all, f, ','))
      {
        maxMacList.push_back (static_cast<uint32_t> (std::stoul (f)));
      }
  }
  if (mobileSf != "fixe" && mobileSf != "sf12" && mobileSf != "oracle")
    {
      NS_FATAL_ERROR ("mobileSf doit valoir fixe, sf12 ou oracle");
    }
  // Lecture des profils : periode_s:octets:nb_noeuds.
  struct Profile
  {
    double periodS;
    uint32_t size;
    uint32_t count;
    bool alert;
  };
  std::vector<Profile> profList;
  if (!profiles.empty ())
    {
      std::istringstream all (profiles);
      std::string item;
      uint32_t total = 0;
      while (std::getline (all, item, ';'))
        {
          Profile pr;
          char c1, c2;
          std::istringstream one (item);
          if (!(one >> pr.periodS >> c1 >> pr.size >> c2 >> pr.count) || c1 != ':' || c2 != ':')
            {
              NS_FATAL_ERROR ("profiles mal forme : " << profiles);
            }
          pr.alert = true;
          total += pr.count;
          profList.push_back (pr);
        }
      if (total != nDevices)
        {
          NS_FATAL_ERROR ("Somme des noeuds par profil (" << total << ") != nDevices (" << nDevices << ")");
        }
      if (!alertProfiles.empty ())
        {
          std::istringstream al (alertProfiles);
          std::string f;
          size_t k = 0;
          while (std::getline (al, f, ',') && k < profList.size ())
            {
              profList[k++].alert = (f == "1");
            }
          if (k != profList.size ())
            {
              NS_FATAL_ERROR ("alertProfiles doit avoir une valeur par profil");
            }
        }
    }

  // ---------------------------------------------------------------------------
  // 2. Graine Monte-Carlo.
  // ---------------------------------------------------------------------------
  RngSeedManager::SetSeed (1);
  RngSeedManager::SetRun (runNumber);

  // ---------------------------------------------------------------------------
  // 3. Le canal, une chaine de maillons : log-distance, puis ombrage si
  //    sigma > 0, puis borne d'horizon si son coefficient est > 0.
  // ---------------------------------------------------------------------------
  Ptr<LogDistancePropagationLossModel> loss =
      CreateObject<LogDistancePropagationLossModel> ();
  loss->SetPathLossExponent (pathLossExp);
  loss->SetReference (refDistM, refLossDb);
  Ptr<PropagationLossModel> lastLink = loss;   // dernier maillon de la chaine

  if (shadowingSigma > 0.0)
    {
      Ptr<NodeShadowingLossModel> shadow = CreateObject<NodeShadowingLossModel> ();
      shadow->SetSigma (shadowingSigma);
      shadow->SetGatewayPositions (gwPosList);   // ombrage par lien noeud-passerelle
      shadow->SetCorrelationDistance (shadowCorrDist);
      shadow->SetSiteCorrelation (shadowSiteCorr);
      lastLink->SetNext (shadow);   // le log-distance passe la main a l'ombrage
      lastLink = shadow;
    }

  if (gwGainDb != 0.0)
    {
      Ptr<GatewayRxGainModel> gain = CreateObject<GatewayRxGainModel> ();
      gain->Set (gwPosList, gwGainDb);
      lastLink->SetNext (gain);
      lastLink = gain;
    }

  if (vegAmDb > 0.0)
    {
      Ptr<VegetationLossModel> veg = CreateObject<VegetationLossModel> ();
      veg->Set (vegAmDb, vegCoef, freqMHz, vegFExp, vegDExp);
      lastLink->SetNext (veg);
      lastLink = veg;
    }

  if (excessLossDb > 0.0)
    {
      Ptr<ExcessLossModel> excess = CreateObject<ExcessLossModel> ();
      excess->SetLoss (excessLossDb);
      lastLink->SetNext (excess);
      lastLink = excess;
    }

  // Consignes v6, point 2 : perte en interieur (UIT-R P.2109), par noeud et
  // dans le temps (calendrier pose plus bas).
  if (indoorLossDb > 0.0 && indoorFraction > 0.0)
    {
      Ptr<IndoorLossModel> indoor = CreateObject<IndoorLossModel> ();
      lastLink->SetNext (indoor);
      lastLink = indoor;
    }

  double horizonMeters = 1000.0 * horizonCoefKm * (std::sqrt (gwHeightM) + std::sqrt (edHeightM));
  if (horizonCoefKm > 0.0)
    {
      Ptr<RadioHorizonLossModel> horizon = CreateObject<RadioHorizonLossModel> ();
      horizon->SetHorizon (horizonMeters, horizonLossDb);
      lastLink->SetNext (horizon);
      lastLink = horizon;
    }

  Ptr<PropagationDelayModel> delay =
      CreateObject<ConstantSpeedPropagationDelayModel> ();
  Ptr<LoraChannel> channel = CreateObject<LoraChannel> (loss, delay);

  // ---------------------------------------------------------------------------
  // 4. Mobilite : noeuds immobiles autour de la passerelle, jusqu'a radius.
  //    disque   : densite uniforme par surface (experience de capacite).
  //    distance : distance uniforme entre 0 et radius, angle uniforme
  //               (experience de portee, meme nombre de noeuds par bande).
  // ---------------------------------------------------------------------------
  MobilityHelper mobility;
  if (placement == "disque")
    {
      mobility.SetPositionAllocator ("ns3::UniformDiscPositionAllocator",
                                     "rho", DoubleValue (radiusMeters),
                                     "X", DoubleValue (0.0),
                                     "Y", DoubleValue (0.0));
    }
  else
    {
      std::ostringstream rho;
      rho << "ns3::UniformRandomVariable[Min=0.0|Max=" << radiusMeters << "]";
      mobility.SetPositionAllocator ("ns3::RandomDiscPositionAllocator",
                                     "Rho", StringValue (rho.str ()),
                                     "X", DoubleValue (0.0),
                                     "Y", DoubleValue (0.0));
    }
  mobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");

  // ---------------------------------------------------------------------------
  // 5. Les assistants.
  // ---------------------------------------------------------------------------
  LoraPhyHelper phyHelper = LoraPhyHelper ();
  phyHelper.SetChannel (channel);
  LorawanMacHelper macHelper = LorawanMacHelper ();
  LoraHelper helper = LoraHelper ();
  helper.EnablePacketTracking ();

  NetworkServerHelper nsHelper = NetworkServerHelper ();
  ForwarderHelper forHelper = ForwarderHelper ();

  // ---------------------------------------------------------------------------
  // 6. Les noeuds.
  // ---------------------------------------------------------------------------
  NodeContainer staticDevices, mobileDevices, endDevices;
  staticDevices.Create (nDevices);
  mobility.Install (staticDevices);
  for (auto j = staticDevices.Begin (); j != staticDevices.End (); ++j)
    {
      Ptr<MobilityModel> m = (*j)->GetObject<MobilityModel> ();
      Vector p = m->GetPosition ();
      p.z = edHeightM;
      m->SetPosition (p);
    }
  // Patients mobiles.
  //   trajet   : WaypointMobilityModel, vitesse constante entre points de
  //              passage (equivalent a ConstantVelocity par morceaux, ce qui
  //              permet l'aller-retour) ;
  //   aleatoire: RandomWaypointMobilityModel dans un rectangle.
  if (mobileCount > 0)
    {
      mobileDevices.Create (mobileCount);
      if (mobModel == "trajet")
        {
          std::vector<Vector> pts;
          std::istringstream all (mobPath);
          std::string item;
          while (std::getline (all, item, ';'))
            {
              double x, y;
              char comma;
              std::istringstream one (item);
              if (!(one >> x >> comma >> y))
                {
                  NS_FATAL_ERROR ("mobPath mal forme : " << mobPath);
                }
              pts.push_back (Vector (x, y, edHeightM));
            }
          if (pts.size () < 1)
            {
              NS_FATAL_ERROR ("mobPath vide");
            }
          MobilityHelper mh;
          mh.SetMobilityModel ("ns3::WaypointMobilityModel");
          mh.Install (mobileDevices);
          for (uint32_t i = 0; i < mobileCount; ++i)
            {
              Ptr<WaypointMobilityModel> wm =
                  mobileDevices.Get (i)->GetObject<WaypointMobilityModel> ();
              double t = mobStart + i * mobStagger;
              wm->AddWaypoint (Waypoint (Seconds (0), pts[0]));
              if (t > 0)
                {
                  wm->AddWaypoint (Waypoint (Seconds (t), pts[0]));
                }
              for (size_t k = 1; k < pts.size (); ++k)
                {
                  double d = std::hypot (pts[k].x - pts[k - 1].x, pts[k].y - pts[k - 1].y);
                  t += d / mobSpeed;
                  wm->AddWaypoint (Waypoint (Seconds (t), pts[k]));
                  if (mobPause > 0)
                    {
                      t += mobPause;
                      wm->AddWaypoint (Waypoint (Seconds (t), pts[k]));
                    }
                }
            }
        }
      else if (mobModel == "aleatoire")
        {
          double x0, x1, y0, y1;
          char c;
          std::istringstream b (mobBounds);
          if (!(b >> x0 >> c >> x1 >> c >> y0 >> c >> y1))
            {
              NS_FATAL_ERROR ("mobBounds mal forme : " << mobBounds);
            }
          std::ostringstream xs, ys, sp, pa;
          xs << "ns3::UniformRandomVariable[Min=" << x0 << "|Max=" << x1 << "]";
          ys << "ns3::UniformRandomVariable[Min=" << y0 << "|Max=" << y1 << "]";
          sp << "ns3::ConstantRandomVariable[Constant=" << mobSpeed << "]";
          pa << "ns3::ConstantRandomVariable[Constant=" << mobPause << "]";
          Ptr<RandomRectanglePositionAllocator> alloc = CreateObject<RandomRectanglePositionAllocator> ();
          alloc->SetAttribute ("X", StringValue (xs.str ()));
          alloc->SetAttribute ("Y", StringValue (ys.str ()));
          alloc->SetAttribute ("Z", DoubleValue (edHeightM));
          MobilityHelper mh;
          mh.SetPositionAllocator (alloc);
          mh.SetMobilityModel ("ns3::RandomWaypointMobilityModel", "Speed", StringValue (sp.str ()),
                               "Pause", StringValue (pa.str ()), "PositionAllocator", PointerValue (alloc));
          mh.Install (mobileDevices);
        }
      else
        {
          NS_FATAL_ERROR ("mobModel doit valoir trajet ou aleatoire");
        }
      for (auto j = mobileDevices.Begin (); j != mobileDevices.End (); ++j)
        {
          g_mobileNodes.insert ((*j)->GetId ());
        }
    }
  endDevices.Add (staticDevices);
  endDevices.Add (mobileDevices);

  uint8_t nwkId = 54;
  uint32_t nwkAddr = 1864;
  Ptr<LoraDeviceAddressGenerator> addrGen =
      CreateObject<LoraDeviceAddressGenerator> (nwkId, nwkAddr);
  macHelper.SetAddressGenerator (addrGen);

  phyHelper.SetDeviceType (LoraPhyHelper::ED);
  macHelper.SetDeviceType (LorawanMacHelper::ED_A);
  helper.Install (phyHelper, macHelper, endDevices);
  // ADR : actif par defaut dans le module 0.3.7, cote serveur
  // (NetworkServerHelper, m_adrEnabled = true) et cote noeud (attribut "ADR").
  // On le pilote explicitement depuis la ligne de commande.
  for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
    {
      Ptr<LorawanMac> m = DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetMac ();
      m->SetAttribute ("ADR", BooleanValue (adr));
    }

  // Mode confirme : chaque noeud demande un acquittement et reessaie jusqu'a
  // nbTrans transmissions. Motif verifie sur un exemple du module 0.3.7.
  if (confirmed)
    {
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          Ptr<LorawanMac> mac =
              DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetMac ();
          Ptr<ClassAEndDeviceLorawanMac> edMac =
              DynamicCast<ClassAEndDeviceLorawanMac> (mac);
          edMac->SetFType (LorawanMacHeader::CONFIRMED_DATA_UP);
          edMac->SetMaxNumberOfTransmissions (nbTrans);
        }
    }

  // Energie radio des noeuds : modele du module (LoraRadioEnergyModel), courants
  // du config. Source tres grande pour ne jamais s'epuiser : on lit la
  // consommation, pas une autonomie.
  std::map<uint32_t, Ptr<energy::DeviceEnergyModel>> energyModels;
  if (energy)
    {
      BasicEnergySourceHelper srcHelper;
      srcHelper.Set ("BasicEnergySourceInitialEnergyJ", DoubleValue (1e9));
      srcHelper.Set ("BasicEnergySupplyVoltageV", DoubleValue (enVoltage));
      // Par defaut la source se met a jour toutes les secondes pour chaque noeud
      // (un milliard d'evenements pour 6400 noeuds sur 2 jours). La consommation
      // est de toute facon cumulee a chaque changement d'etat de la radio : une
      // mise a jour par jour suffit.
      srcHelper.Set ("PeriodicEnergyUpdateInterval", TimeValue (Days (1)));
      LoraRadioEnergyModelHelper radioEnergy;
      radioEnergy.Set ("SleepCurrentA", DoubleValue (enSleepA));
      radioEnergy.Set ("StandbyCurrentA", DoubleValue (enStandbyA));
      radioEnergy.Set ("RxCurrentA", DoubleValue (enRxA));
      radioEnergy.SetTxCurrentModel ("ns3::LinearLoraTxCurrentModel", "Eta", DoubleValue (enTxEta),
                                     "Voltage", DoubleValue (enVoltage),
                                     "BaseCurrent", DoubleValue (enTxBaseA));
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          energy::EnergySourceContainer src = srcHelper.Install (*j);
          energy::DeviceEnergyModelContainer dm = radioEnergy.Install ((*j)->GetDevice (0), src);
          energyModels[(*j)->GetId ()] = dm.Get (0);
          // Le PHY du module demarre en attente (STANDBY, 1,4 mA) et y reste
          // jusqu'a la premiere emission : on le met en sommeil a t = 0, comme
          // une radio reelle entre deux trames.
          Ptr<EndDeviceLoraPhy> edPhy = DynamicCast<EndDeviceLoraPhy> (
              DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetPhy ());
          Simulator::ScheduleNow (&PhySleep, edPhy);
        }
    }

  // ---------------------------------------------------------------------------
  // 7. Les passerelles, aux positions donnees (une seule au centre par defaut).
  // ---------------------------------------------------------------------------
  NodeContainer gateways;
  gateways.Create (gwPosList.size ());
  Ptr<ListPositionAllocator> gwAlloc = CreateObject<ListPositionAllocator> ();
  for (const Vector &v : gwPosList)
    {
      gwAlloc->Add (v);
    }
  mobility.SetPositionAllocator (gwAlloc);
  mobility.Install (gateways);
  phyHelper.SetDeviceType (LoraPhyHelper::GW);
  macHelper.SetDeviceType (LorawanMacHelper::GW);
  helper.Install (phyHelper, macHelper, gateways);
  // Puissance RX2 : la sous-bande 869,4-869,65 MHz du module vaut 27 dBm
  // (ETSI). La decision ARCEP 2020-320 ne fixe pas de puissance : scenario
  // reglementaire a 14 dBm par rx2PowerDbm (consignes v4, point 10).
  for (auto g = gateways.Begin (); g != gateways.End (); ++g)
    {
      auto gwMac = DynamicCast<LoraNetDevice> ((*g)->GetDevice (0))->GetMac ();
      auto sb = gwMac->GetLogicalLoraChannelHelper ()->GetSubBandFromFrequency (869525000);
      if (sb)
        {
          sb->SetMaxTxPowerDbm (rx2PowerDbm);
        }
    }

  // Canaux separes (option). Le canal du module programme un evenement de
  // reception pour chaque radio a chaque emission : cout en N^2. Ici les
  // montantes ne sont livrees qu'aux passerelles et les descendantes qu'aux
  // noeuds. Effet de bord a connaitre : le recepteur d'un noeud ne voit plus
  // les montantes des autres noeuds comme interference pendant ses fenetres de
  // reception (le module ignore l'isolation par inversion IQ), ni les
  // passerelles les descendantes des autres passerelles.
  if (splitChannel)
    {
      Ptr<LoraChannel> downChannel = CreateObject<LoraChannel> (loss, delay);
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          Ptr<LoraPhy> phy = DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetPhy ();
          channel->Remove (phy);       // n'entend plus les montantes
          downChannel->Add (phy);      // entend les descendantes
        }
      for (auto g = gateways.Begin (); g != gateways.End (); ++g)
        {
          Ptr<LoraPhy> phy = DynamicCast<LoraNetDevice> ((*g)->GetDevice (0))->GetPhy ();
          phy->SetChannel (downChannel);   // emet ses descendantes vers les noeuds
        }
    }

  // Branchement de la trace par noeud (voir le bloc NodeStats plus haut).
  if (nodeTrace)
    {
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          uint32_t id = (*j)->GetId ();
          g_nodeStats[id] = NodeStats ();
          Ptr<LoraNetDevice> dev = DynamicCast<LoraNetDevice> ((*j)->GetDevice (0));
          Ptr<LorawanMac> mac = dev->GetMac ();
          mac->TraceConnectWithoutContext ("SentNewPacket",
                                           MakeBoundCallback (&OnMacNewPacket, id));
          mac->TraceConnectWithoutContext ("ConfirmedTransmissionOutcome",
                                           MakeBoundCallback (&OnConfirmedOutcome, id));
          dev->GetPhy ()->TraceConnectWithoutContext (
              "StartSending", MakeBoundCallback (&OnPhyStartSending, mac));
        }
      for (uint32_t g = 0; g < gateways.GetN (); ++g)
        {
          Ptr<LoraNetDevice> dev = DynamicCast<LoraNetDevice> (gateways.Get (g)->GetDevice (0));
          dev->GetMac ()->TraceConnectWithoutContext ("ReceivedPacket",
                                                      MakeBoundCallback (&OnGwMacReceived, g));
        }
      // Passerelle la plus proche de chaque noeud, fixee au depart.
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          Vector p = (*j)->GetObject<MobilityModel> ()->GetPosition ();
          double best = 1e300;
          for (uint32_t g = 0; g < gwPosList.size (); ++g)
            {
              double d = std::hypot (p.x - gwPosList[g].x, p.y - gwPosList[g].y);
              if (d < best)
                {
                  best = d;
                  g_nodeNearestGw[(*j)->GetId ()] = g;
                }
            }
        }
    }

  // ---------------------------------------------------------------------------
  // 8. Attribution des Spreading Factors selon la distance.
  // ---------------------------------------------------------------------------
  // Calendrier interieur / exterieur (consignes v6, point 2). Chaque jour, le
  // pont passe une seule plage dehors, de duree (1 - indoorFraction) x 24 h,
  // qui commence entre 6 h et 22 h moins sa duree (tirage par noeud et par
  // jour) ; le reste du temps, la nuit et le matin, il est dedans. Fraction 1 :
  // toujours dedans. Pose avant l'attribution des SF, faite a t = 0 (nuit,
  // dedans).
  if (indoorLossDb > 0.0 && indoorFraction > 0.0)
    {
      Ptr<UniformRandomVariable> ui = CreateObject<UniformRandomVariable> ();
      double outH = (1.0 - std::min (1.0, indoorFraction)) * 24.0;
      int days = static_cast<int> (std::ceil (simTimeSeconds / 86400.0)) + 1;
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          uint32_t id = (*j)->GetId ();
          g_indoorNow[id] = indoorLossDb;
          if (outH <= 0.0)
            {
              continue;
            }
          for (int d = 0; d < days; ++d)
            {
              double latest = std::max (6.0, 22.0 - outH);
              double start = d * 24.0 + ui->GetValue (6.0, latest);
              Simulator::Schedule (Seconds (start * 3600.0), &SetIndoor, id, 0.0);
              Simulator::Schedule (Seconds ((start + outH) * 3600.0), &SetIndoor, id, indoorLossDb);
            }
        }
    }
  LorawanMacHelper::SetSpreadingFactorsUp (endDevices, gateways, channel);
  g_gwPos = gwPosList;
  g_channelPtr = channel;
  g_gatewaysForSf = gateways;
  if (mobileSf == "sf12")
    {
      for (auto j = mobileDevices.Begin (); j != mobileDevices.End (); ++j)
        {
          DynamicCast<EndDeviceLorawanMac> (
              DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetMac ())->SetDataRate (0);
        }
    }
  // Adresse -> noeud, et descendantes des passerelles (choix de la passerelle
  // pour l'acquittement des mobiles).
  for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
    {
      Ptr<EndDeviceLorawanMac> m = DynamicCast<EndDeviceLorawanMac> (
          DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetMac ());
      g_addrToNode[m->GetDeviceAddress ().Get ()] = (*j)->GetId ();
    }
  if (mobileCount > 0)
    {
      for (uint32_t g = 0; g < gateways.GetN (); ++g)
        {
          DynamicCast<LoraNetDevice> (gateways.Get (g)->GetDevice (0))->GetMac ()->TraceConnectWithoutContext (
              "SentNewPacket", MakeBoundCallback (&OnGwDownlink, g));
        }
    }

  // ---------------------------------------------------------------------------
  // 9. Le trafic.
  // ---------------------------------------------------------------------------
  //    Sans profils : emetteur periodique du module, identique pour tous.
  //    Avec profils : une application ProfileSender par noeud ; les noeuds sont
  //    affectes aux profils par blocs d'indices, ce qui equivaut a un tirage
  //    aleatoire puisque les positions sont tirees independamment.
  ApplicationContainer apps;
  if (profList.empty ())
    {
      PeriodicSenderHelper appHelper = PeriodicSenderHelper ();
      appHelper.SetPeriod (Seconds (appPeriodSeconds));
      appHelper.SetPacketSize (packetSize);
      apps = appHelper.Install (endDevices);
    }
  else
    {
      ProfileSender::Params base;
      base.micBytes = micBytes;
      base.routineConfirmed = confirmed;
      base.routineNbTrans = confirmed ? nbTrans : 1;
      base.alertSize = alertSize;
      base.alertNbTrans = alertNbTrans;
      base.deferDuringAlert = deferDuringAlert;
      base.alertConfirmed = alertConfirmed;
      base.confGuard = Seconds (confGuardS);
      base.sfw = sfw;
      base.probeEvery = sfwProbeEvery;
      base.bufferMax = sfwBuffer;
      base.flushInterval = Seconds (sfwFlush);
      base.sfwNbTrans = sfwNbTrans;
      base.maxMacPayload = maxMacList;
      base.recap = recap;
      base.recapPeriod = Hours (recapPeriodH);
      base.recapRequest = Hours (recapRequestH);
      base.recapAlarm = Hours (recapAlarmH);
      base.recapBuffer = Hours (recapBufferH);
      base.alarmTwoStage = alarmTwoStage;
      base.alarmPendingMax = Hours (alarmPendingMaxH);
      auto install = [&] (Ptr<Node> node, double periodS, uint32_t frameSize, bool alert, int profIdx,
                          bool oracle) {
        Ptr<ClassAEndDeviceLorawanMac> mac = DynamicCast<ClassAEndDeviceLorawanMac> (
            DynamicCast<LoraNetDevice> (node->GetDevice (0))->GetMac ());
        ProfileSender::Params pr = base;
        pr.routinePeriod = Seconds (periodS);
        // La taille de profil inclut le MIC (convention de l'orchestrateur) :
        // on la ramene a la taille d'une mesure.
        pr.readingSize = (frameSize > micBytes) ? frameSize - micBytes : frameSize;
        pr.alertPerDay = alert ? alertPerDay : 0.0;
        pr.sfOracle = oracle;
        Ptr<ProfileSender> app = CreateObject<ProfileSender> ();
        app->Configure (mac, node, pr);
        node->AddApplication (app);
        apps.Add (app);
        g_nodeStats[node->GetId ()].profile = profIdx;
      };
      uint32_t idx = 0;
      for (uint32_t k = 0; k < profList.size (); ++k)
        {
          for (uint32_t c = 0; c < profList[k].count; ++c, ++idx)
            {
              install (staticDevices.Get (idx), profList[k].periodS, profList[k].size, profList[k].alert,
                       static_cast<int> (k), false);
            }
        }
      // Mobiles : profil propre (ou profil 0).
      double mPeriod = profList[0].periodS;
      uint32_t mSize = profList[0].size;
      if (!mobileProfile.empty ())
        {
          char c;
          std::istringstream one (mobileProfile);
          uint32_t reading;
          if (!(one >> mPeriod >> c >> reading))
            {
              NS_FATAL_ERROR ("mobileProfile mal forme : " << mobileProfile);
            }
          mSize = reading + micBytes;
        }
      for (auto j = mobileDevices.Begin (); j != mobileDevices.End (); ++j)
        {
          install (*j, mPeriod, mSize, mobileAlert, -2, mobileSf == "oracle");
          g_nodeStats[(*j)->GetId ()].mobile = true;
        }
    }
  apps.Start (Seconds (0));
  apps.Stop (Seconds (simTimeSeconds));

  // ---------------------------------------------------------------------------
  // 10. Le serveur central et le lien point a point passerelle -> serveur.
  // ---------------------------------------------------------------------------
  Ptr<Node> networkServer = CreateObject<Node> ();
  PointToPointHelper p2p;
  p2p.SetDeviceAttribute ("DataRate", StringValue ("5Mbps"));
  p2p.SetChannelAttribute ("Delay", TimeValue (MilliSeconds (backhaulDelayMs)));
  P2PGwRegistration_t gwRegistration;
  for (auto gw = gateways.Begin (); gw != gateways.End (); ++gw)
    {
      auto c = p2p.Install (networkServer, *gw);
      auto dev = DynamicCast<PointToPointNetDevice> (c.Get (0));
      gwRegistration.emplace_back (dev, *gw);
    }
  nsHelper.SetGatewaysP2P (gwRegistration);
  nsHelper.EnableAdr (adr);
  nsHelper.SetEndDevices (endDevices);
  nsHelper.Install (networkServer);
  forHelper.Install (gateways);
  if (nodeTrace)
    {
      networkServer->GetApplication (0)->TraceConnectWithoutContext (
          "ReceivedPacket", MakeCallback (&OnNsReceived));
    }

  // ---------------------------------------------------------------------------
  // 11. Lancement.
  // ---------------------------------------------------------------------------
  Simulator::Stop (Seconds (simTimeSeconds) + Hours (1));
  Simulator::Run ();

  // ---------------------------------------------------------------------------
  // 12. Resultats.
  //     Ordre du vecteur PHY verifie dans lora-packet-tracker.cc :
  //     0 total, 1 recus, 2 interferes, 3 sans recepteur libre,
  //     4 sous la sensibilite, 5 perdus pendant une emission passerelle.
  // ---------------------------------------------------------------------------
  LoraPacketTracker &tracker = helper.GetPacketTracker ();
  Time winStop = Seconds (simTimeSeconds) + Hours (1);

  std::string macGlobal = tracker.CountMacPacketsGlobally (Seconds (0), winStop);
  std::istringstream iss (macGlobal);
  double sent = 0, received = 0;
  iss >> sent >> received;
  double pdr = (sent > 0) ? (received / sent) : 0.0;

  // Compteurs PHY sommes sur toutes les passerelles (identiques au cas a une
  // passerelle quand il n'y en a qu'une).
  long phyCnt[6] = {0, 0, 0, 0, 0, 0};
  for (uint32_t g = 0; g < gateways.GetN (); ++g)
    {
      std::vector<int> phy = tracker.CountPhyPacketsPerGw (Seconds (0), winStop,
                                                           gateways.Get (g)->GetId ());
      for (size_t k = 0; k < 6 && k < phy.size (); ++k)
        {
          phyCnt[k] += phy[k];
        }
    }
  long phyTotal = phyCnt[0], phyRecv = phyCnt[1], phyInterf = phyCnt[2];
  long phyNoRecv = phyCnt[3], phyUnderSens = phyCnt[4], phyLostTx = phyCnt[5];
  long gwReceptionsAll = 0, multiGwAll = 0;
  for (const auto &kv : g_nodeStats)
    {
      gwReceptionsAll += kv.second.gwReceptions;
      multiGwAll += kv.second.multiGw;
    }

  // En confirme, CPSR rend "envoyees acquittees" : succes de l'aller-retour.
  long   acked = -1;
  double cpsr = -1.0;
  if (confirmed)
    {
      std::string cpsrStr = tracker.CountMacPacketsGloballyCpsr (Seconds (0), winStop);
      std::istringstream iss2 (cpsrStr);
      double csent = 0, cack = 0;
      iss2 >> csent >> cack;
      acked = (long) cack;
      cpsr = (csent > 0) ? (cack / csent) : 0.0;
    }

  // Lignes NODE preparees avant Destroy, tant que noeuds et MAC existent.
  std::ostringstream nodeLines;
  std::map<uint32_t, std::string> v6;
  if (nodeTrace)
    {
      for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
        {
          uint32_t id = (*j)->GetId ();
          Vector p = (*j)->GetObject<MobilityModel> ()->GetPosition ();
          // Distance a la passerelle la plus proche, et son indice.
          double dist = 1e300;
          uint32_t nearest = 0;
          for (uint32_t g = 0; g < gwPosList.size (); ++g)
            {
              double d = std::hypot (p.x - gwPosList[g].x, p.y - gwPosList[g].y);
              if (d < dist)
                {
                  dist = d;
                  nearest = g;
                }
            }
          Ptr<EndDeviceLorawanMac> edMac = DynamicCast<EndDeviceLorawanMac> (
              DynamicCast<LoraNetDevice> ((*j)->GetDevice (0))->GetMac ());
          unsigned sf = edMac->GetSfFromDataRate (edMac->GetDataRate ());
          if (energyModels.count (id))
            {
              g_nodeStats[id].energyJ = energyModels[id]->GetTotalEnergyConsumption ();
            }
          const NodeStats &s = g_nodeStats[id];
          if (!v6.count (id))
            {
              v6[id] = V6Fields (id, simTimeSeconds, evalExcludeLastS);
            }
          nodeLines << "NODE;"
                    << expLabel << ";" << zoneLabel << ";" << nDevices << ";"
                    << runNumber << ";" << (confirmed ? 1 : 0) << ";"
                    << id << ";"
                    << std::fixed << std::setprecision (1) << dist << ";"
                    << sf << ";"
                    << s.newSent << ";" << s.txTotal << ";" << s.received << ";"
                    << (confirmed ? (long) s.acked : -1L) << ";"
                    << std::setprecision (4) << s.airtimeS << ";"
                    << nearest << ";" << s.gwReceptions << ";" << s.multiGw << ";"
                    << std::setprecision (4)
                    << (s.received > 0 ? s.latencySumS / s.received : -1.0) << ";"
                    << (s.received > 0 ? s.latencyMaxS : -1.0) << ";"
                    << s.rxNearest << ";"
                    << s.profile << ";" << s.genRoutine << ";" << s.genAlert << ";"
                    << s.alertNew << ";" << s.alertDelivered << ";" << s.alertAcked << ";"
                    << std::setprecision (4) << s.alertLatUpMaxS << ";"
                    << (s.alertAcked > 0 ? s.alertRttSumS / s.alertAcked : -1.0) << ";"
                    << s.alertRttMaxS << ";"
                    << (s.mobile ? 1 : 0) << ";" << s.readingsGen << ";" << s.readingsDelivered << ";"
                    << s.readingsDropped << ";"
                    << (s.readingsDelivered > 0 ? s.readingLatSumS / s.readingsDelivered : -1.0) << ";"
                    << s.readingLatMaxS << ";"
                    << s.confRoutineGen << ";" << s.confRoutineAcked << ";" << s.confRoutineFail << ";"
                    << (s.confRoutineAcked > 0 ? s.confRoutineDelaySumS / s.confRoutineAcked : -1.0) << ";"
                    << s.confRoutineDelayMaxS << ";"
                    << std::setprecision (6) << s.energyJ << ";"
                    << v6.at (id) << "\n";
          nodeLines.unsetf (std::ios::floatfield);
        }
    }

  Simulator::Destroy ();

  // ---------------------------------------------------------------------------
  // 13. Ligne machine.
  //     exp;zone;nDevices;pathLossExp;shadowingSigma;runNumber;
  //     sent;received;pdr;phyTotal;phyRecv;phyInterf;phyNoRecv;
  //     phyUnderSens;phyLostTx;confirmed;nbTrans;acked;cpsr;
  //     nGateways;gwReceptions;multiGwPackets;nsArrivals
  //     (compteurs phy sommes sur toutes les passerelles)
  // ---------------------------------------------------------------------------
  std::cout << "CSV;"
            << expLabel << ";"
            << zoneLabel << ";"
            << nDevices << ";"
            << pathLossExp << ";"
            << shadowingSigma << ";"
            << runNumber << ";"
            << (long) sent << ";"
            << (long) received << ";"
            << pdr << ";"
            << phyTotal << ";"
            << phyRecv << ";"
            << phyInterf << ";"
            << phyNoRecv << ";"
            << phyUnderSens << ";"
            << phyLostTx << ";"
            << (confirmed ? 1 : 0) << ";"
            << nbTrans << ";"
            << acked << ";"
            << cpsr << ";"
            << gateways.GetN () << ";"
            << gwReceptionsAll << ";"
            << multiGwAll << ";"
            << g_nsArrivals
            << std::endl;

  // Delais d'acquittement, une ligne par type de trame confirmee :
  //   ACK;exp;zone;nDevices;run;kind;nConf;nAcked;nFail;nOpen;p50;p95;p99;
  //       p95Acquittees;max;gardes;remisEnFile
  //   kind : routine ou alerte. Delai = production -> acquittement. Une trame
  //   non acquittee (echec ou sans issue a la fin) compte comme delai infini.
  for (int kind = 0; kind <= 1; ++kind)
    {
      std::vector<double> all, ok;
      uint32_t nFail = 0, nOpen = 0;
      for (const ConfFrame &f : g_confFrames)
        {
          if (f.kind != kind)
            {
              continue;
            }
          if (f.done && f.acked)
            {
              all.push_back (f.delay);
              ok.push_back (f.delay);
            }
          else
            {
              all.push_back (std::numeric_limits<double>::infinity ());
              (f.done ? nFail : nOpen)++;
            }
        }
      if (all.empty ())
        {
          continue;
        }
      std::sort (all.begin (), all.end ());
      std::sort (ok.begin (), ok.end ());
      auto q = [] (const std::vector<double> &v, double pc) {
        if (v.empty ())
          {
            return std::numeric_limits<double>::quiet_NaN ();
          }
        double k = (v.size () - 1) * pc;
        size_t i = static_cast<size_t> (k);
        if (i + 1 >= v.size () || std::isinf (v[i + 1]))
          {
            return v[std::min (v.size () - 1, (size_t) std::ceil (k))];
          }
        return v[i] + (k - i) * (v[i + 1] - v[i]);
      };
      std::cout << "ACK;" << expLabel << ";" << zoneLabel << ";" << nDevices << ";" << runNumber << ";"
                << (kind == 0 ? "routine" : "alerte") << ";" << all.size () << ";" << ok.size () << ";"
                << nFail << ";" << nOpen << ";" << std::setprecision (6) << q (all, 0.50) << ";"
                << q (all, 0.95) << ";" << q (all, 0.99) << ";" << q (ok, 0.95) << ";"
                << (ok.empty () ? -1.0 : ok.back ()) << ";" << g_guardFires << ";" << g_requeued << "\n";
    }

  // Consignes v6 : delai production -> premiere reception des alertes (non
  // livree = infini), toutes puis a l'interieur seulement. Colonnes reprises
  // de la ligne ACK avec ce sens :
  //   nConf alertes comptees ; nAcked livrees en 15 min ; nFail alarmes du pont ;
  //   nOpen fausses alarmes (alerte livree mais non acquittee) ; p50, p95, p99 ;
  //   p95Acquittees : alertes acquittees ; max : plus long delai livre ;
  //   gardes : alertes non acquittees sans alarme (doit valoir 0) ;
  //   remisEnFile : alertes livrees.
  for (int in = 0; in <= 1; ++in)
    {
      std::vector<double> d, okd;
      uint32_t n = 0, ok15 = 0, al = 0, fal = 0, unc = 0, ack = 0, deliv = 0;
      for (const AlertRec &a : g_alertRecs)
        {
          if (a.tGen > simTimeSeconds - 900.0 || (in == 1 && !a.indoor))
            {
              continue;
            }
          n++;
          double l = a.delivered ? a.tDeliv - a.tGen : std::numeric_limits<double>::infinity ();
          d.push_back (l);
          if (a.delivered)
            {
              okd.push_back (l);
              deliv++;
            }
          ok15 += (a.delivered && l <= 900.0);
          al += a.alarm;
          fal += (a.alarm && a.delivered);
          unc += (!a.acked && !a.alarm);
          ack += a.acked;
        }
      std::sort (d.begin (), d.end ());
      std::sort (okd.begin (), okd.end ());
      auto q = [] (const std::vector<double> &v, double pq) {
        if (v.empty ())
          {
            return -1.0;
          }
        double k = pq * (v.size () - 1);
        size_t i = static_cast<size_t> (k);
        if (i + 1 >= v.size () || std::isinf (v[i + 1]))
          {
            return v[std::min (i + (k > i ? 1 : 0), v.size () - 1)];
          }
        return v[i] + (k - i) * (v[i + 1] - v[i]);
      };
      std::cout << "ACK;" << expLabel << ";" << zoneLabel << ";" << nDevices << ";" << runNumber << ";"
                << (in ? "alerte_interieur" : "alerte_reseau") << ";" << n << ";" << ok15 << ";" << al << ";"
                << fal << ";" << std::setprecision (6) << q (d, 0.50) << ";" << q (d, 0.95) << ";" << q (d, 0.99)
                << ";" << ack << ";" << (okd.empty () ? -1.0 : okd.back ()) << ";" << unc << ";" << deliv << "\n";
    }
  // Remontee (module) : nConf reponses a envoyer ; nAcked parties en RX1 ;
  // nFail trop tard pour RX1 et RX2 ; nOpen RX1 trop tard rattrapees en RX2 ;
  // p50, p95, p99 de l'aller-retour tire ; p95Acquittees : visees d'emblee en
  // RX2 ; max : aller-retour maximal.
  if (bhModel)
    {
      std::vector<double> r = NetworkScheduler::s_bhRtt;
      std::sort (r.begin (), r.end ());
      auto qq = [&r] (double pq) { return r.empty () ? -1.0 : r[std::min (r.size () - 1, (size_t) (pq * r.size ()))]; };
      std::cout << "ACK;" << expLabel << ";" << zoneLabel << ";" << nDevices << ";" << runNumber << ";remontee;"
                << NetworkScheduler::s_bhReplies << ";" << NetworkScheduler::s_bhRx1 << ";"
                << NetworkScheduler::s_bhLost << ";" << NetworkScheduler::s_bhRx2Fallback << ";"
                << qq (0.5) << ";" << qq (0.95) << ";" << qq (0.99) << ";" << NetworkScheduler::s_bhRx2Target << ";"
                << (r.empty () ? -1.0 : r.back ()) << ";0;0\n";
    }

  // Trace par noeud, apres la ligne CSV.
  std::cout << nodeLines.str ();

  // Traces des mobiles : par trame (PKT), descendantes (DL), par mesure (RD).
  //   PKT;noeud;t;x;y;dPlusProche;gwPlusProche;sf;type;nMesures;livree;latence;nGw
  //       type : 0 routine, 1 alerte, 2 sonde, 3 lot de store-and-forward
  //   DL;t;noeud;passerelle
  //   RD;noeud;numero;tProduction;x;y;livree;tLivraison;perdueTampon
  for (const auto &po : g_pktOrder)
    {
      const PktRec &r = g_pktRec[po.first];
      std::cout << "PKT;" << r.node << ";" << std::fixed << std::setprecision (2) << r.t << ";"
                << std::setprecision (1) << r.x << ";" << r.y << ";" << r.dNear << ";" << r.nearGw << ";"
                << r.sf << ";" << r.kind << ";" << r.nReadings << ";" << (r.delivered ? 1 : 0) << ";"
                << std::setprecision (4) << r.lat << ";" << r.gws.size () << "\n";
    }
  for (const auto &d : g_downlinks)
    {
      std::cout << "DL;" << std::fixed << std::setprecision (2) << std::get<0> (d) << ";"
                << std::get<1> (d) << ";" << std::get<2> (d) << "\n";
    }
  for (uint32_t id : g_mobileNodes)
    {
      const std::vector<Reading> &v = g_readings[id];
      for (size_t q = 0; q < v.size (); ++q)
        {
          std::cout << "RD;" << id << ";" << q << ";" << std::fixed << std::setprecision (2) << v[q].tGen
                    << ";" << std::setprecision (1) << v[q].x << ";" << v[q].y << ";"
                    << (v[q].delivered ? 1 : 0) << ";" << std::setprecision (2) << v[q].tDeliv << ";"
                    << (v[q].dropped ? 1 : 0) << "\n";
        }
    }
  std::cout.unsetf (std::ios::floatfield);

  // ---------------------------------------------------------------------------
  // 14. Resume lisible.
  // ---------------------------------------------------------------------------
  std::cout << "\n";
  std::cout << "  +---------------------------------------------------+\n";
  std::cout << "  |   Cellule LoRaWAN STOP-MNT - AVEC ombrage         |\n";
  std::cout << "  +---------------------------------------------------+\n";
  std::cout << "    Experience          : " << expLabel << "\n";
  std::cout << "    Zone                : " << zoneLabel << "\n";
  std::cout << "    Noeuds              : " << nDevices << "\n";
  std::cout << "    Exposant de perte   : " << pathLossExp << "\n";
  std::cout << "    Ombrage sigma (dB)  : " << shadowingSigma
            << (shadowingSigma > 0.0 ? "" : "  (desactive)") << "\n";
  std::cout << "    Horizon radio (m)   : ";
  if (horizonCoefKm > 0.0) std::cout << horizonMeters << "\n";
  else std::cout << "desactive\n";
  std::cout << "    Placement           : " << placement << "\n";
  std::cout << "    Ancrage             : " << refLossDb << " dB a " << refDistM << " m"
            << (excessLossDb > 0.0 ? ", + vegetation " : "")
            << (excessLossDb > 0.0 ? std::to_string (excessLossDb) + " dB" : "") << "\n";
  std::cout << "    Passerelles         : " << gwPosList.size () << "  (" << gwPositions << ")\n";
  std::cout << "    ADR                 : " << (adr ? "actif" : "desactive (SF fixe par bilan)") << "\n";
  std::cout << "    Rayon cellule (m)   : " << radiusMeters << "\n";
  std::cout << "    Run                 : " << runNumber << "\n";
  std::cout << "    Mode                : "
            << (confirmed ? "confirme" : "non confirme");
  if (confirmed) std::cout << "  (nbTrans max = " << nbTrans << ")";
  std::cout << "\n";
  std::cout << "  ---------------------------------------------------\n";
  std::cout << "    Trames MAC envoyees : " << (long) sent << "\n";
  std::cout << "    Trames MAC recues   : " << (long) received << "\n";
  std::cout << "    Taux de livraison   : "
            << std::fixed << std::setprecision (2) << (pdr * 100.0) << " %\n";
  if (confirmed)
    {
      std::cout << "    Acquittees (CPSR)   : " << acked
                << "   soit " << std::fixed << std::setprecision (2)
                << (cpsr * 100.0) << " % d'aller-retour reussis\n";
    }
  std::cout << "  ----- detail physique a la passerelle -------------\n";
  std::cout << "    Total vues          : " << phyTotal << "\n";
  std::cout << "    Recues              : " << phyRecv << "\n";
  std::cout << "    Interferees         : " << phyInterf << "\n";
  std::cout << "    Sans recepteur libre: " << phyNoRecv << "\n";
  std::cout << "    Sous la sensibilite : " << phyUnderSens << "\n";
  std::cout << "    Perdues (TX passer.): " << phyLostTx << "\n";
  std::cout << "  +---------------------------------------------------+\n\n";

  return 0;
}
