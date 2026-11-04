/*
 * lte-cell.cc
 *
 * Volet cellulaire du projet STOP-MNT : le pont patient relaie ses mesures par
 * un modem 4G (le module LTE de ns-3 ne couvre que la 4G, pas la 2G ni la 3G).
 *
 * Meme cadre que le modele LoRa, pour comparer a armes egales :
 *   - meme propagation par zone : log-distance ancre (d0, PL(d0), n), puis
 *     ombrage par lien UE-eNodeB, correle dans l'espace pour les mobiles, puis
 *     terme de vegetation eventuel (stopmnt-propagation.h, partage) ;
 *   - memes placements (disque ou distance), memes profils patients, memes
 *     scenarios de mobilite (trajet par points de passage, marche aleatoire) ;
 *   - memes sorties : ligne CSV, une ligne NODE par UE au format du modele LoRa
 *     (les colonnes sans objet en LTE valent -1), lignes PKT par paquet pour les
 *     mobiles, et lignes HO pour les handovers.
 *
 * Limites du module LTE de ns-3, a ecrire dans le memoire :
 *   - l'UE reste en etat connecte (RRC_CONNECTED) toute la simulation : pas de
 *     passage repos -> connecte, donc ni latence d'acces ni signalisation de
 *     connexion ; elles s'ajoutent a la main depuis les datasheets ;
 *   - pas de PSM ni d'eDRX, pas de modele d'energie du modem : energie a la main ;
 *   - simulation au millieme de seconde (subframe) : durees simulees courtes et
 *     cadence d'instrumentation, au lieu des cadences cliniques ;
 *   - au plus 320 UE par cellule (periodicite SRS maximale).
 *
 * Sortie :
 *   CSV;exp;zone;nUes;n;sigma;run;sent;received;pdr;nEnbs;hoStart;hoOk;hoErreur
 *   NODE;... (format du modele LoRa)
 *   PKT;noeud;t;x;y;dPlusProche;enbPlusProche;-1;type;1;livre;latence;celluleServante
 *   HO;t;noeud;celluleSource;celluleCible;issue (debut, ok, erreur)
 */

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/lte-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/propagation-module.h"
#include "ns3/spectrum-module.h"
#include "stopmnt-propagation.h"

#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("StopMntLteCell");

// -----------------------------------------------------------------------------
// Etiquette portee par chaque paquet applicatif : noeud, numero, type, instant.
// ByteTag : elle survit a la traversee de la pile LTE et du coeur EPC.
// -----------------------------------------------------------------------------
class StopMntTag : public Tag
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::StopMntTag").SetParent<Tag> ().AddConstructor<StopMntTag> ();
    return tid;
  }
  TypeId GetInstanceTypeId (void) const override { return GetTypeId (); }
  uint32_t GetSerializedSize (void) const override { return 4 + 4 + 1 + 8; }
  void Serialize (TagBuffer i) const override
  {
    i.WriteU32 (node);
    i.WriteU32 (seq);
    i.WriteU8 (kind);
    i.WriteU64 (static_cast<uint64_t> (tSendNs));
  }
  void Deserialize (TagBuffer i) override
  {
    node = i.ReadU32 ();
    seq = i.ReadU32 ();
    kind = i.ReadU8 ();
    tSendNs = static_cast<int64_t> (i.ReadU64 ());
  }
  void Print (std::ostream &os) const override { os << node << ":" << seq; }

  uint32_t node = 0;
  uint32_t seq = 0;
  uint8_t kind = 0;   // 0 routine, 1 alerte
  int64_t tSendNs = 0;
};

// -----------------------------------------------------------------------------
// Statistiques par UE et suivi par paquet.
// -----------------------------------------------------------------------------
struct UeStats
{
  int profile = -1;
  bool mobile = false;
  uint32_t genRoutine = 0, genAlert = 0;
  uint32_t sent = 0, received = 0;
  uint32_t alertDelivered = 0;
  double latSum = 0.0, latMax = 0.0;
  double alertLatMax = 0.0;
};
static std::map<uint32_t, UeStats> g_ue;

struct LtePkt
{
  uint32_t node;
  double t, x, y, dNear;
  int nearEnb, kind, cell;
  bool delivered = false;
  double lat = -1.0;
};
static std::map<std::pair<uint32_t, uint32_t>, LtePkt> g_pkt;   // (noeud, numero)
static std::vector<std::pair<uint32_t, uint32_t>> g_pktOrder;
static std::set<uint32_t> g_mobile;
static std::vector<Vector> g_enbPos;
static std::map<uint64_t, uint32_t> g_imsiToNode;
static std::map<uint32_t, uint16_t> g_servingCell;               // noeud -> cellule
static std::vector<std::tuple<double, uint32_t, int, int, std::string>> g_ho;
static uint32_t g_hoStart = 0, g_hoOk = 0, g_hoErr = 0;

static int
NearestEnb (const Vector &p, double &dist)
{
  dist = 1e300;
  int best = 0;
  for (size_t g = 0; g < g_enbPos.size (); ++g)
    {
      double d = std::hypot (p.x - g_enbPos[g].x, p.y - g_enbPos[g].y);
      if (d < dist)
        {
          dist = d;
          best = static_cast<int> (g);
        }
    }
  return best;
}

// Reception au serveur distant : premiere arrivee d'un paquet etiquete.
static void
OnSinkRx (Ptr<const Packet> p, const Address &from)
{
  StopMntTag tag;
  if (!p->FindFirstMatchingByteTag (tag))
    {
      return;
    }
  auto key = std::make_pair (tag.node, tag.seq);
  double lat = Simulator::Now ().GetSeconds () - tag.tSendNs * 1e-9;
  UeStats &s = g_ue[tag.node];
  auto it = g_pkt.find (key);
  if (it != g_pkt.end ())
    {
      if (it->second.delivered)
        {
          return;
        }
      it->second.delivered = true;
      it->second.lat = lat;
    }
  s.received++;
  s.latSum += lat;
  s.latMax = std::max (s.latMax, lat);
  if (tag.kind == 1)
    {
      s.alertDelivered++;
      s.alertLatMax = std::max (s.alertLatMax, lat);
    }
}

static void
OnHoStart (std::string ctx, uint64_t imsi, uint16_t cellId, uint16_t rnti, uint16_t target)
{
  g_hoStart++;
  auto it = g_imsiToNode.find (imsi);
  if (it != g_imsiToNode.end () && g_mobile.count (it->second))
    {
      g_ho.emplace_back (Simulator::Now ().GetSeconds (), it->second, cellId, target, "debut");
    }
}

static void
OnHoOk (std::string ctx, uint64_t imsi, uint16_t cellId, uint16_t rnti)
{
  g_hoOk++;
  auto it = g_imsiToNode.find (imsi);
  if (it != g_imsiToNode.end ())
    {
      g_servingCell[it->second] = cellId;
      if (g_mobile.count (it->second))
        {
          g_ho.emplace_back (Simulator::Now ().GetSeconds (), it->second, -1, cellId, "ok");
        }
    }
}

static void
OnHoErr (std::string ctx, uint64_t imsi, uint16_t cellId, uint16_t rnti)
{
  g_hoErr++;
  auto it = g_imsiToNode.find (imsi);
  if (it != g_imsiToNode.end () && g_mobile.count (it->second))
    {
      g_ho.emplace_back (Simulator::Now ().GetSeconds (), it->second, cellId, -1, "erreur");
    }
}

static void
OnConnEstablished (std::string ctx, uint64_t imsi, uint16_t cellId, uint16_t rnti)
{
  auto it = g_imsiToNode.find (imsi);
  if (it != g_imsiToNode.end ())
    {
      g_servingCell[it->second] = cellId;
    }
}

// -----------------------------------------------------------------------------
// Application de profil patient cote UE : routine periodique et alerte de
// Poisson superposee, en UDP vers le serveur distant.
// -----------------------------------------------------------------------------
class LteProfileSender : public Application
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid = TypeId ("ns3::LteProfileSender").SetParent<Application> ().AddConstructor<LteProfileSender> ();
    return tid;
  }

  void Configure (Address peer, Time period, uint32_t size, double alertPerDay, uint32_t alertSize)
  {
    m_peer = peer;
    m_period = period;
    m_size = size;
    m_alertPerDay = alertPerDay;
    m_alertSize = alertSize;
  }

private:
  void StartApplication () override
  {
    m_socket = Socket::CreateSocket (GetNode (), UdpSocketFactory::GetTypeId ());
    m_socket->Bind ();
    m_socket->Connect (m_peer);
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable> ();
    m_ev = Simulator::Schedule (Seconds (u->GetValue (0, m_period.GetSeconds ())), &LteProfileSender::Routine, this);
    if (m_alertPerDay > 0)
      {
        m_expo = CreateObject<ExponentialRandomVariable> ();
        m_expo->SetAttribute ("Mean", DoubleValue (86400.0 / m_alertPerDay));
        m_evA = Simulator::Schedule (Seconds (m_expo->GetValue ()), &LteProfileSender::Alert, this);
      }
  }
  void StopApplication () override
  {
    Simulator::Cancel (m_ev);
    Simulator::Cancel (m_evA);
  }
  void Emit (uint32_t size, uint8_t kind)
  {
    uint32_t id = GetNode ()->GetId ();
    Ptr<Packet> p = Create<Packet> (size);
    StopMntTag tag;
    tag.node = id;
    tag.seq = m_seq++;
    tag.kind = kind;
    tag.tSendNs = Simulator::Now ().GetNanoSeconds ();
    p->AddByteTag (tag);
    UeStats &s = g_ue[id];
    s.sent++;
    if (g_mobile.count (id))
      {
        Vector pos = GetNode ()->GetObject<MobilityModel> ()->GetPosition ();
        LtePkt r;
        r.node = id;
        r.t = Simulator::Now ().GetSeconds ();
        r.x = pos.x;
        r.y = pos.y;
        r.nearEnb = NearestEnb (pos, r.dNear);
        r.kind = kind;
        r.cell = g_servingCell.count (id) ? g_servingCell[id] : -1;
        g_pkt[std::make_pair (id, tag.seq)] = r;
        g_pktOrder.emplace_back (id, tag.seq);
      }
    m_socket->Send (p);
  }
  void Routine ()
  {
    g_ue[GetNode ()->GetId ()].genRoutine++;
    Emit (m_size, 0);
    m_ev = Simulator::Schedule (m_period, &LteProfileSender::Routine, this);
  }
  void Alert ()
  {
    g_ue[GetNode ()->GetId ()].genAlert++;
    Emit (m_alertSize, 1);
    m_evA = Simulator::Schedule (Seconds (m_expo->GetValue ()), &LteProfileSender::Alert, this);
  }

  Ptr<Socket> m_socket;
  Address m_peer;
  Time m_period;
  uint32_t m_size = 0;
  double m_alertPerDay = 0;
  uint32_t m_alertSize = 0;
  uint32_t m_seq = 0;
  Ptr<ExponentialRandomVariable> m_expo;
  EventId m_ev, m_evA;
};

static std::vector<Vector>
ParsePoints (const std::string &s, double z, const char *nom)
{
  std::vector<Vector> pts;
  std::istringstream all (s);
  std::string item;
  while (std::getline (all, item, ';'))
    {
      double x, y;
      char c;
      std::istringstream one (item);
      if (!(one >> x >> c >> y))
        {
          NS_FATAL_ERROR (nom << " mal forme : " << s);
        }
      pts.push_back (Vector (x, y, z));
    }
  return pts;
}

int
main (int argc, char *argv[])
{
  // Parametres, tous fournis par l'orchestrateur depuis le config.
  uint32_t nDevices = 20;
  double radiusMeters = 3000.0;
  std::string placement = "disque";
  double pathLossExp = 2.32, refDistM = 1000.0, refLossDb = 128.95, excessLossDb = 0.0;
  double shadowingSigma = 7.8, shadowCorrDist = 0.0;
  double shadowSiteCorr = 0.0;
  std::string enbPositions = "0,0";
  double enbHeightM = 30.0, ueHeightM = 1.5;
  double enbTxPowerDbm = 46.0, ueTxPowerDbm = 23.0;
  double enbNoiseFigureDb = 5.0, ueNoiseFigureDb = 9.0;
  uint32_t bandwidthRb = 50;
  uint32_t dlEarfcn = 6200, ulEarfcn = 24200;
  std::string rlcMode = "am";
  uint32_t srsPeriodicity = 320;
  std::string hoAlgo = "a3";
  double hoHysteresisDb = 3.0;
  double hoTttMs = 256.0;
  double backhaulDelayMs = 0.0;
  std::string profiles = "60:20:20";   // periode_s:octets:nb_ue
  double alertPerDay = 0.0;
  uint32_t alertSize = 12;
  double simTimeSeconds = 600.0;
  uint32_t runNumber = 1;
  std::string zoneLabel = "na", expLabel = "lte";
  bool nodeTrace = true;
  uint32_t mobileCount = 0;
  std::string mobModel = "trajet", mobPath = "", mobBounds = "", mobileProfile = "";
  double mobSpeed = 1.4, mobPause = 0.0, mobStart = 0.0, mobStagger = 0.0;
  bool mobileAlert = true;

  CommandLine cmd (__FILE__);
  cmd.AddValue ("nDevices", "Nombre d'UE fixes", nDevices);
  cmd.AddValue ("radius", "Rayon de placement (m)", radiusMeters);
  cmd.AddValue ("placement", "disque ou distance", placement);
  cmd.AddValue ("pathLossExp", "Exposant de perte", pathLossExp);
  cmd.AddValue ("refDist", "Distance de reference d0 (m)", refDistM);
  cmd.AddValue ("refLoss", "Perte a d0 (dB)", refLossDb);
  cmd.AddValue ("excessLossDb", "Perte en exces (vegetation), dB", excessLossDb);
  cmd.AddValue ("shadowingSigma", "Ecart-type d'ombrage (dB)", shadowingSigma);
  cmd.AddValue ("shadowCorrDist", "Distance de decorrelation de l'ombrage (m)", shadowCorrDist);
  cmd.AddValue ("shadowSiteCorr", "Correlation de l'ombrage entre sites (0 a 1)", shadowSiteCorr);
  cmd.AddValue ("gwPositions", "Positions des eNodeB x1,y1;x2,y2 (m)", enbPositions);
  cmd.AddValue ("gwHeight", "Hauteur des eNodeB (m)", enbHeightM);
  cmd.AddValue ("edHeight", "Hauteur des UE (m)", ueHeightM);
  cmd.AddValue ("enbTxPower", "Puissance eNodeB (dBm)", enbTxPowerDbm);
  cmd.AddValue ("ueTxPower", "Puissance max UE (dBm)", ueTxPowerDbm);
  cmd.AddValue ("enbNoiseFigure", "Facteur de bruit eNodeB (dB)", enbNoiseFigureDb);
  cmd.AddValue ("ueNoiseFigure", "Facteur de bruit UE (dB)", ueNoiseFigureDb);
  cmd.AddValue ("bandwidthRb", "Largeur de bande en blocs de ressources", bandwidthRb);
  cmd.AddValue ("dlEarfcn", "EARFCN descendant", dlEarfcn);
  cmd.AddValue ("ulEarfcn", "EARFCN montant", ulEarfcn);
  cmd.AddValue ("rlcMode", "Mode RLC : am ou um", rlcMode);
  cmd.AddValue ("srsPeriodicity", "Periodicite SRS (ms), plafonne les UE par cellule", srsPeriodicity);
  cmd.AddValue ("hoAlgo", "Algorithme de handover : a3 ou aucun", hoAlgo);
  cmd.AddValue ("hoHysteresis", "Hysteresis de l'evenement A3 (dB)", hoHysteresisDb);
  cmd.AddValue ("hoTtt", "Time-to-trigger de l'evenement A3 (ms)", hoTttMs);
  cmd.AddValue ("backhaulDelayMs", "Delai du lien PGW -> serveur (ms)", backhaulDelayMs);
  cmd.AddValue ("profiles", "Profils periode_s:octets:nb_ue;...", profiles);
  cmd.AddValue ("alertPerDay", "Alertes par jour et par UE", alertPerDay);
  cmd.AddValue ("alertSize", "Taille d'une alerte (octets)", alertSize);
  cmd.AddValue ("simTime", "Duree simulee (s)", simTimeSeconds);
  cmd.AddValue ("runNumber", "Numero de run", runNumber);
  cmd.AddValue ("zoneLabel", "Etiquette de zone", zoneLabel);
  cmd.AddValue ("expLabel", "Etiquette d'experience", expLabel);
  cmd.AddValue ("nodeTrace", "Lignes NODE (0/1)", nodeTrace);
  cmd.AddValue ("mobileCount", "UE mobiles ajoutes", mobileCount);
  cmd.AddValue ("mobModel", "trajet ou aleatoire", mobModel);
  cmd.AddValue ("mobPath", "Points de passage x1,y1;x2,y2", mobPath);
  cmd.AddValue ("mobSpeed", "Vitesse (m/s)", mobSpeed);
  cmd.AddValue ("mobPause", "Pause aux points (s)", mobPause);
  cmd.AddValue ("mobStart", "Depart du premier mobile (s)", mobStart);
  cmd.AddValue ("mobStagger", "Decalage entre mobiles (s)", mobStagger);
  cmd.AddValue ("mobBounds", "Zone aleatoire xmin,xmax,ymin,ymax", mobBounds);
  cmd.AddValue ("mobileProfile", "Profil des mobiles periode_s:octets", mobileProfile);
  cmd.AddValue ("mobileAlert", "Alertes pour les mobiles (0/1)", mobileAlert);
  cmd.Parse (argc, argv);

  RngSeedManager::SetSeed (1);
  RngSeedManager::SetRun (runNumber);

  g_enbPos = ParsePoints (enbPositions, enbHeightM, "gwPositions");

  // Profils.
  struct Prof { double period; uint32_t size; uint32_t count; };
  std::vector<Prof> prof;
  {
    std::istringstream all (profiles);
    std::string item;
    uint32_t total = 0;
    while (std::getline (all, item, ';'))
      {
        Prof p;
        char c1, c2;
        std::istringstream one (item);
        if (!(one >> p.period >> c1 >> p.size >> c2 >> p.count))
          {
            NS_FATAL_ERROR ("profiles mal forme : " << profiles);
          }
        prof.push_back (p);
        total += p.count;
      }
    if (total != nDevices)
      {
        NS_FATAL_ERROR ("Somme des UE par profil (" << total << ") != nDevices (" << nDevices << ")");
      }
  }

  // --- LTE et propagation -----------------------------------------------------
  Config::SetDefault ("ns3::LteEnbRrc::SrsPeriodicity", UintegerValue (srsPeriodicity));
  Config::SetDefault ("ns3::LteEnbRrc::EpsBearerToRlcMapping",
                      EnumValue (rlcMode == "am" ? LteEnbRrc::RLC_AM_ALWAYS : LteEnbRrc::RLC_UM_ALWAYS));
  Config::SetDefault ("ns3::LteEnbPhy::TxPower", DoubleValue (enbTxPowerDbm));
  Config::SetDefault ("ns3::LteUePhy::TxPower", DoubleValue (ueTxPowerDbm));
  Config::SetDefault ("ns3::LteEnbPhy::NoiseFigure", DoubleValue (enbNoiseFigureDb));
  Config::SetDefault ("ns3::LteUePhy::NoiseFigure", DoubleValue (ueNoiseFigureDb));
  Config::SetDefault ("ns3::LteEnbNetDevice::DlBandwidth", UintegerValue (bandwidthRb));
  Config::SetDefault ("ns3::LteEnbNetDevice::UlBandwidth", UintegerValue (bandwidthRb));
  Config::SetDefault ("ns3::LteEnbNetDevice::DlEarfcn", UintegerValue (dlEarfcn));
  Config::SetDefault ("ns3::LteEnbNetDevice::UlEarfcn", UintegerValue (ulEarfcn));
  Config::SetDefault ("ns3::LteUeNetDevice::DlEarfcn", UintegerValue (dlEarfcn));

  Ptr<LteHelper> lte = CreateObject<LteHelper> ();
  Ptr<PointToPointEpcHelper> epc = CreateObject<PointToPointEpcHelper> ();
  lte->SetEpcHelper (epc);
  lte->SetAttribute ("PathlossModel", StringValue ("ns3::LogDistancePropagationLossModel"));
  lte->SetPathlossModelAttribute ("Exponent", DoubleValue (pathLossExp));
  lte->SetPathlossModelAttribute ("ReferenceDistance", DoubleValue (refDistM));
  lte->SetPathlossModelAttribute ("ReferenceLoss", DoubleValue (refLossDb));
  if (hoAlgo == "a3")
    {
      lte->SetHandoverAlgorithmType ("ns3::A3RsrpHandoverAlgorithm");
      lte->SetHandoverAlgorithmAttribute ("Hysteresis", DoubleValue (hoHysteresisDb));
      lte->SetHandoverAlgorithmAttribute ("TimeToTrigger", TimeValue (MilliSeconds (hoTttMs)));
    }
  else
    {
      lte->SetHandoverAlgorithmType ("ns3::NoOpHandoverAlgorithm");
    }

  // Coeur : serveur distant relie au PGW.
  Ptr<Node> pgw = epc->GetPgwNode ();
  NodeContainer remote;
  remote.Create (1);
  InternetStackHelper internet;
  internet.Install (remote);
  PointToPointHelper p2p;
  p2p.SetDeviceAttribute ("DataRate", DataRateValue (DataRate ("10Gb/s")));
  p2p.SetChannelAttribute ("Delay", TimeValue (MilliSeconds (backhaulDelayMs)));
  NetDeviceContainer inet = p2p.Install (pgw, remote.Get (0));
  Ipv4AddressHelper ipv4h;
  ipv4h.SetBase ("1.0.0.0", "255.0.0.0");
  Ipv4InterfaceContainer inetIf = ipv4h.Assign (inet);
  Ipv4Address remoteAddr = inetIf.GetAddress (1);
  Ipv4StaticRoutingHelper routing;
  routing.GetStaticRouting (remote.Get (0)->GetObject<Ipv4> ())
      ->AddNetworkRouteTo (Ipv4Address ("7.0.0.0"), Ipv4Mask ("255.0.0.0"), 1);

  // eNodeB.
  NodeContainer enbs;
  enbs.Create (g_enbPos.size ());
  Ptr<ListPositionAllocator> ea = CreateObject<ListPositionAllocator> ();
  for (const Vector &v : g_enbPos)
    {
      ea->Add (v);
    }
  MobilityHelper em;
  em.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  em.SetPositionAllocator (ea);
  em.Install (enbs);

  // UE fixes.
  NodeContainer staticUes, mobileUes, ues;
  staticUes.Create (nDevices);
  MobilityHelper um;
  if (placement == "disque")
    {
      um.SetPositionAllocator ("ns3::UniformDiscPositionAllocator", "rho", DoubleValue (radiusMeters),
                               "X", DoubleValue (0.0), "Y", DoubleValue (0.0), "Z", DoubleValue (ueHeightM));
    }
  else
    {
      std::ostringstream rho;
      rho << "ns3::UniformRandomVariable[Min=0.0|Max=" << radiusMeters << "]";
      um.SetPositionAllocator ("ns3::RandomDiscPositionAllocator", "Rho", StringValue (rho.str ()),
                               "X", DoubleValue (0.0), "Y", DoubleValue (0.0), "Z", DoubleValue (ueHeightM));
    }
  um.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  um.Install (staticUes);

  // UE mobiles (memes modeles que le LoRa).
  if (mobileCount > 0)
    {
      mobileUes.Create (mobileCount);
      if (mobModel == "trajet")
        {
          std::vector<Vector> pts = ParsePoints (mobPath, ueHeightM, "mobPath");
          MobilityHelper mh;
          mh.SetMobilityModel ("ns3::WaypointMobilityModel");
          mh.Install (mobileUes);
          for (uint32_t i = 0; i < mobileCount; ++i)
            {
              Ptr<WaypointMobilityModel> wm = mobileUes.Get (i)->GetObject<WaypointMobilityModel> ();
              double t = mobStart + i * mobStagger;
              wm->AddWaypoint (Waypoint (Seconds (0), pts[0]));
              if (t > 0)
                {
                  wm->AddWaypoint (Waypoint (Seconds (t), pts[0]));
                }
              for (size_t k = 1; k < pts.size (); ++k)
                {
                  t += std::hypot (pts[k].x - pts[k - 1].x, pts[k].y - pts[k - 1].y) / mobSpeed;
                  wm->AddWaypoint (Waypoint (Seconds (t), pts[k]));
                  if (mobPause > 0)
                    {
                      t += mobPause;
                      wm->AddWaypoint (Waypoint (Seconds (t), pts[k]));
                    }
                }
            }
        }
      else
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
          alloc->SetAttribute ("Z", DoubleValue (ueHeightM));
          MobilityHelper mh;
          mh.SetPositionAllocator (alloc);
          mh.SetMobilityModel ("ns3::RandomWaypointMobilityModel", "Speed", StringValue (sp.str ()),
                               "Pause", StringValue (pa.str ()), "PositionAllocator", PointerValue (alloc));
          mh.Install (mobileUes);
        }
      for (auto j = mobileUes.Begin (); j != mobileUes.End (); ++j)
        {
          g_mobile.insert ((*j)->GetId ());
        }
    }
  ues.Add (staticUes);
  ues.Add (mobileUes);

  NetDeviceContainer enbDevs = lte->InstallEnbDevice (enbs);
  NetDeviceContainer ueDevs = lte->InstallUeDevice (ues);

  // Ombrage par lien et vegetation, chaines derriere le log-distance, sur les
  // deux canaux (montant et descendant) avec le meme objet : reciprocite.
  Ptr<NodeShadowingLossModel> shadow;
  if (shadowingSigma > 0.0)
    {
      shadow = CreateObject<NodeShadowingLossModel> ();
      shadow->SetSigma (shadowingSigma);
      shadow->SetGatewayPositions (g_enbPos);
      shadow->SetCorrelationDistance (shadowCorrDist);
      shadow->SetSiteCorrelation (shadowSiteCorr);
    }
  Ptr<ExcessLossModel> excess;
  if (excessLossDb > 0.0)
    {
      excess = CreateObject<ExcessLossModel> ();
      excess->SetLoss (excessLossDb);
    }
  for (Ptr<SpectrumChannel> ch : {lte->GetUplinkSpectrumChannel (), lte->GetDownlinkSpectrumChannel ()})
    {
      if (shadow)
        {
          ch->AddPropagationLossModel (shadow);
        }
      if (excess)
        {
          ch->AddPropagationLossModel (excess);
        }
    }

  internet.Install (ues);
  Ipv4InterfaceContainer ueIf = epc->AssignUeIpv4Address (ueDevs);
  for (uint32_t u = 0; u < ues.GetN (); ++u)
    {
      routing.GetStaticRouting (ues.Get (u)->GetObject<Ipv4> ())
          ->SetDefaultRoute (epc->GetUeDefaultGatewayAddress (), 1);
      g_imsiToNode[DynamicCast<LteUeNetDevice> (ueDevs.Get (u))->GetImsi ()] = ues.Get (u)->GetId ();
    }
  lte->Attach (ueDevs);   // selection de cellule initiale par le module
  if (enbs.GetN () > 1)
    {
      lte->AddX2Interface (enbs);
    }

  // Serveur distant : puits UDP.
  uint16_t port = 9000;
  PacketSinkHelper sinkH ("ns3::UdpSocketFactory", InetSocketAddress (Ipv4Address::GetAny (), port));
  ApplicationContainer sink = sinkH.Install (remote.Get (0));
  sink.Get (0)->TraceConnectWithoutContext ("Rx", MakeCallback (&OnSinkRx));
  sink.Start (Seconds (0));

  // Applications de profil.
  ApplicationContainer apps;
  auto install = [&] (Ptr<Node> n, double period, uint32_t size, int profIdx, bool alert) {
    Ptr<LteProfileSender> a = CreateObject<LteProfileSender> ();
    a->Configure (InetSocketAddress (remoteAddr, port), Seconds (period), size, alert ? alertPerDay : 0.0,
                  alertSize);
    n->AddApplication (a);
    apps.Add (a);
    g_ue[n->GetId ()].profile = profIdx;
  };
  uint32_t idx = 0;
  for (uint32_t k = 0; k < prof.size (); ++k)
    {
      for (uint32_t c = 0; c < prof[k].count; ++c, ++idx)
        {
          install (staticUes.Get (idx), prof[k].period, prof[k].size, static_cast<int> (k), true);
        }
    }
  double mPeriod = prof[0].period;
  uint32_t mSize = prof[0].size;
  if (!mobileProfile.empty ())
    {
      char c;
      std::istringstream one (mobileProfile);
      one >> mPeriod >> c >> mSize;
    }
  for (auto j = mobileUes.Begin (); j != mobileUes.End (); ++j)
    {
      install (*j, mPeriod, mSize, -2, mobileAlert);
      g_ue[(*j)->GetId ()].mobile = true;
    }
  // Demarrage apres l'attachement initial (procedure d'acces non modelisee
  // comme cout : elle n'existe qu'au debut en etat connecte).
  apps.Start (Seconds (1.0));
  apps.Stop (Seconds (simTimeSeconds));

  Config::Connect ("/NodeList/*/DeviceList/*/LteUeRrc/HandoverStart", MakeCallback (&OnHoStart));
  Config::Connect ("/NodeList/*/DeviceList/*/LteUeRrc/HandoverEndOk", MakeCallback (&OnHoOk));
  Config::Connect ("/NodeList/*/DeviceList/*/LteUeRrc/HandoverEndError", MakeCallback (&OnHoErr));
  Config::Connect ("/NodeList/*/DeviceList/*/LteUeRrc/ConnectionEstablished",
                   MakeCallback (&OnConnEstablished));

  Simulator::Stop (Seconds (simTimeSeconds + 2.0));
  Simulator::Run ();

  // --- Sorties ----------------------------------------------------------------
  uint64_t sent = 0, received = 0;
  std::ostringstream nodeLines;
  for (auto j = ues.Begin (); j != ues.End (); ++j)
    {
      uint32_t id = (*j)->GetId ();
      const UeStats &s = g_ue[id];
      sent += s.sent;
      received += s.received;
      if (!nodeTrace)
        {
          continue;
        }
      Vector p = (*j)->GetObject<MobilityModel> ()->GetPosition ();
      double d;
      int near = NearestEnb (p, d);
      double latMean = s.received ? s.latSum / s.received : -1.0;
      // Format du modele LoRa ; colonnes sans objet en LTE a -1.
      nodeLines << "NODE;" << expLabel << ";" << zoneLabel << ";" << nDevices << ";" << runNumber << ";0;" << id
                << ";" << std::fixed << std::setprecision (1) << d << ";-1;" << s.sent << ";" << s.sent << ";"
                << s.received << ";-1;-1;" << near << ";" << s.received << ";-1;" << std::setprecision (4)
                << latMean << ";" << (s.received ? s.latMax : -1.0) << ";-1;" << s.profile << ";"
                << s.genRoutine << ";" << s.genAlert << ";" << s.genAlert << ";" << s.alertDelivered << ";-1;"
                << s.alertLatMax << ";-1;-1;" << (s.mobile ? 1 : 0) << ";" << s.genRoutine << ";"
                << (s.received - s.alertDelivered) << ";0;-1;-1\n";
      nodeLines.unsetf (std::ios::floatfield);
    }
  std::cout << "CSV;" << expLabel << ";" << zoneLabel << ";" << nDevices << ";" << pathLossExp << ";"
            << shadowingSigma << ";" << runNumber << ";" << sent << ";" << received << ";"
            << (sent ? double (received) / sent : 0.0) << ";" << enbs.GetN () << ";" << g_hoStart << ";"
            << g_hoOk << ";" << g_hoErr << std::endl;
  std::cout << nodeLines.str ();
  for (const auto &k : g_pktOrder)
    {
      const LtePkt &r = g_pkt[k];
      std::cout << "PKT;" << r.node << ";" << std::fixed << std::setprecision (2) << r.t << ";"
                << std::setprecision (1) << r.x << ";" << r.y << ";" << r.dNear << ";" << r.nearEnb << ";-1;"
                << r.kind << ";1;" << (r.delivered ? 1 : 0) << ";" << std::setprecision (4) << r.lat << ";"
                << r.cell << "\n";
    }
  for (const auto &h : g_ho)
    {
      std::cout << "HO;" << std::fixed << std::setprecision (3) << std::get<0> (h) << ";" << std::get<1> (h)
                << ";" << std::get<2> (h) << ";" << std::get<3> (h) << ";" << std::get<4> (h) << "\n";
    }
  std::cout.unsetf (std::ios::floatfield);
  std::cout << "\n  Cellule LTE STOP-MNT : " << ues.GetN () << " UE, " << enbs.GetN () << " eNodeB, livraison "
            << (sent ? 100.0 * received / sent : 0.0) << " % (" << received << "/" << sent << "), handovers "
            << g_hoOk << " reussis / " << g_hoStart << " commences\n";
  Simulator::Destroy ();
  return 0;
}
