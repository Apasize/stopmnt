/*
 * lorawan-cell.cc
 *
 * Modele d'une cellule LoRaWAN representative pour le projet STOP-MNT.
 *
 * Construit sur la structure du code STOP-MNT deja eprouve (lora-palier1.cc),
 * qui compile et tourne sur ns-3.48 + module lorawan signetlabdei 0.3.7.
 * On y ajoute : l'exposant de perte reglable (propagation par zone), le numero
 * de run pour les repetitions Monte-Carlo, les etiquettes recopiees en sortie,
 * et une ligne CSV unique pour l'orchestrateur Python.
 *
 * Principe : aucune valeur en dur. Tout arrive par la ligne de commande.
 * L'orchestrateur lit le config.json et appelle ce programme pour chaque point
 * de balayage et chaque repetition.
 *
 * Sortie : une seule ligne prefixee "CSV;" sur la sortie standard.
 *
 * Note sur l'ombrage : le modele d'ombrage correle du module fige l'ecart-type
 * a 4 dB (non reglable). Un ombrage par zone, tel que prevu dans la table, n'est
 * donc pas applique dans cette version ; seul le log-distance l'est. Decision a
 * prendre pour une version ulterieure.
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/lorawan-module.h"

#include <sstream>
#include <vector>
#include <string>
#include <iomanip>

using namespace ns3;
using namespace lorawan;

NS_LOG_COMPONENT_DEFINE ("LorawanCell");

int
main (int argc, char *argv[])
{
  // ---------------------------------------------------------------------------
  // 1. Parametres, tous surchargeables en ligne de commande.
  // ---------------------------------------------------------------------------
  uint32_t nDevices = 100;              // nombre de noeuds
  double   radiusMeters = 4000.0;       // rayon de la cellule, en metres
  double   pathLossExp = 3.3;           // exposant de perte (par zone)
  double   refLoss1mDb = 7.7;           // perte de reference a 1 m
  double   appPeriodSeconds = 8640.0;   // periode d'emission
  uint32_t packetSize = 33;             // charge physique en octets (20 utile + 13 entete)
  double   simTimeSeconds = 172800.0;   // duree simulee (2 jours)
  double   gwHeightM = 15.0;            // hauteur antenne passerelle
  double   edHeightM = 1.2;             // hauteur antenne noeud
  uint32_t runNumber = 1;               // numero de run (graine Monte-Carlo)
  double   shadowingSigma = 0.0;        // recopie en sortie seulement, non applique (voir note)
  std::string zoneLabel = "na";
  std::string expLabel = "capacite";

  CommandLine cmd (__FILE__);
  cmd.AddValue ("nDevices", "Nombre de noeuds", nDevices);
  cmd.AddValue ("radius", "Rayon de la cellule en metres", radiusMeters);
  cmd.AddValue ("pathLossExp", "Exposant de perte", pathLossExp);
  cmd.AddValue ("refLoss", "Perte de reference a 1 m en dB", refLoss1mDb);
  cmd.AddValue ("appPeriod", "Periode d'emission en secondes", appPeriodSeconds);
  cmd.AddValue ("pktSize", "Taille de la charge physique en octets", packetSize);
  cmd.AddValue ("simTime", "Duree simulee en secondes", simTimeSeconds);
  cmd.AddValue ("gwHeight", "Hauteur antenne passerelle en metres", gwHeightM);
  cmd.AddValue ("edHeight", "Hauteur antenne noeud en metres", edHeightM);
  cmd.AddValue ("runNumber", "Numero de run (graine)", runNumber);
  cmd.AddValue ("shadowingSigma", "Ecart-type d'ombrage (recopie seulement, non applique)", shadowingSigma);
  cmd.AddValue ("zoneLabel", "Etiquette de zone, recopiee en sortie", zoneLabel);
  cmd.AddValue ("expLabel", "Etiquette d'experience, recopiee en sortie", expLabel);
  cmd.Parse (argc, argv);

  // ---------------------------------------------------------------------------
  // 2. Graine Monte-Carlo.
  // ---------------------------------------------------------------------------
  RngSeedManager::SetSeed (1);
  RngSeedManager::SetRun (runNumber);

  // ---------------------------------------------------------------------------
  // 3. Le canal : log-distance, parametre par l'exposant de la zone.
  // ---------------------------------------------------------------------------
  Ptr<LogDistancePropagationLossModel> loss =
      CreateObject<LogDistancePropagationLossModel> ();
  loss->SetPathLossExponent (pathLossExp);
  loss->SetReference (1, refLoss1mDb);

  Ptr<PropagationDelayModel> delay =
      CreateObject<ConstantSpeedPropagationDelayModel> ();
  Ptr<LoraChannel> channel = CreateObject<LoraChannel> (loss, delay);

  // ---------------------------------------------------------------------------
  // 4. Mobilite : noeuds immobiles, repartis dans un disque autour du centre.
  // ---------------------------------------------------------------------------
  MobilityHelper mobility;
  mobility.SetPositionAllocator ("ns3::UniformDiscPositionAllocator",
                                 "rho", DoubleValue (radiusMeters),
                                 "X", DoubleValue (0.0),
                                 "Y", DoubleValue (0.0));
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
  NodeContainer endDevices;
  endDevices.Create (nDevices);
  mobility.Install (endDevices);
  for (auto j = endDevices.Begin (); j != endDevices.End (); ++j)
    {
      Ptr<MobilityModel> m = (*j)->GetObject<MobilityModel> ();
      Vector p = m->GetPosition ();
      p.z = edHeightM;
      m->SetPosition (p);
    }

  uint8_t nwkId = 54;
  uint32_t nwkAddr = 1864;
  Ptr<LoraDeviceAddressGenerator> addrGen =
      CreateObject<LoraDeviceAddressGenerator> (nwkId, nwkAddr);
  macHelper.SetAddressGenerator (addrGen);

  phyHelper.SetDeviceType (LoraPhyHelper::ED);
  macHelper.SetDeviceType (LorawanMacHelper::ED_A);
  helper.Install (phyHelper, macHelper, endDevices);

  // ---------------------------------------------------------------------------
  // 7. La passerelle, une seule, au centre.
  // ---------------------------------------------------------------------------
  NodeContainer gateways;
  gateways.Create (1);
  Ptr<ListPositionAllocator> gwAlloc = CreateObject<ListPositionAllocator> ();
  gwAlloc->Add (Vector (0.0, 0.0, gwHeightM));
  mobility.SetPositionAllocator (gwAlloc);
  mobility.Install (gateways);
  phyHelper.SetDeviceType (LoraPhyHelper::GW);
  macHelper.SetDeviceType (LorawanMacHelper::GW);
  helper.Install (phyHelper, macHelper, gateways);

  // ---------------------------------------------------------------------------
  // 8. Attribution des Spreading Factors selon la distance.
  // ---------------------------------------------------------------------------
  LorawanMacHelper::SetSpreadingFactorsUp (endDevices, gateways, channel);

  // ---------------------------------------------------------------------------
  // 9. Le trafic.
  // ---------------------------------------------------------------------------
  PeriodicSenderHelper appHelper = PeriodicSenderHelper ();
  appHelper.SetPeriod (Seconds (appPeriodSeconds));
  appHelper.SetPacketSize (packetSize);
  ApplicationContainer apps = appHelper.Install (endDevices);
  apps.Start (Seconds (0));
  apps.Stop (Seconds (simTimeSeconds));

  // ---------------------------------------------------------------------------
  // 10. Le serveur central et le lien point a point passerelle -> serveur.
  // ---------------------------------------------------------------------------
  Ptr<Node> networkServer = CreateObject<Node> ();
  PointToPointHelper p2p;
  p2p.SetDeviceAttribute ("DataRate", StringValue ("5Mbps"));
  p2p.SetChannelAttribute ("Delay", StringValue ("2ms"));
  P2PGwRegistration_t gwRegistration;
  for (auto gw = gateways.Begin (); gw != gateways.End (); ++gw)
    {
      auto c = p2p.Install (networkServer, *gw);
      auto dev = DynamicCast<PointToPointNetDevice> (c.Get (0));
      gwRegistration.emplace_back (dev, *gw);
    }
  nsHelper.SetGatewaysP2P (gwRegistration);
  nsHelper.SetEndDevices (endDevices);
  nsHelper.Install (networkServer);
  forHelper.Install (gateways);

  // ---------------------------------------------------------------------------
  // 11. Lancement.
  // ---------------------------------------------------------------------------
  Simulator::Stop (Seconds (simTimeSeconds) + Hours (1));
  Simulator::Run ();

  // ---------------------------------------------------------------------------
  // 12. Resultats. Le traceur renvoie "envoyes recus" en MAC global.
  //     CountPhyPacketsPerGw donne les causes de perte cote PHY.
  // ---------------------------------------------------------------------------
  LoraPacketTracker &tracker = helper.GetPacketTracker ();
  Time winStop = Seconds (simTimeSeconds) + Hours (1);

  std::string macGlobal = tracker.CountMacPacketsGlobally (Seconds (0), winStop);
  std::istringstream iss (macGlobal);
  double sent = 0, received = 0;
  iss >> sent >> received;
  double pdr = (sent > 0) ? (received / sent) : 0.0;

  // Ordre exact du vecteur, verifie dans lora-packet-tracker.cc :
  // 0 total, 1 recus, 2 interferes, 3 sans recepteur libre,
  // 4 sous la sensibilite, 5 perdus pendant une emission passerelle.
  std::vector<int> phy = tracker.CountPhyPacketsPerGw (Seconds (0), winStop,
                                                       gateways.Get (0)->GetId ());
  long phyTotal     = (phy.size () > 0) ? phy[0] : -1;
  long phyRecv      = (phy.size () > 1) ? phy[1] : -1;
  long phyInterf    = (phy.size () > 2) ? phy[2] : -1;
  long phyNoRecv    = (phy.size () > 3) ? phy[3] : -1;
  long phyUnderSens = (phy.size () > 4) ? phy[4] : -1;
  long phyLostTx    = (phy.size () > 5) ? phy[5] : -1;

  Simulator::Destroy ();

  // ---------------------------------------------------------------------------
  // 13. Sortie CSV sur une seule ligne, prefixee "CSV;".
  //     Colonnes : exp;zone;nDevices;pathLossExp;shadowingSigma;runNumber;
  //                sent;received;pdr;phyTotal;phyRecv;phyInterf;
  //                phyNoRecv;phyUnderSens;phyLostTx
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
            << phyLostTx
            << std::endl;

  // ---------------------------------------------------------------------------
  // 14. Resume lisible, pour l'oeil humain quand on lance a la main.
  //     La ligne machine ci-dessus reste la seule que l'orchestrateur lit.
  // ---------------------------------------------------------------------------
  std::cout << "\n";
  std::cout << "  +---------------------------------------------------+\n";
  std::cout << "  |        Cellule LoRaWAN STOP-MNT - resultat        |\n";
  std::cout << "  +---------------------------------------------------+\n";
  std::cout << "    Experience          : " << expLabel << "\n";
  std::cout << "    Zone                : " << zoneLabel << "\n";
  std::cout << "    Noeuds              : " << nDevices << "\n";
  std::cout << "    Exposant de perte   : " << pathLossExp << "\n";
  std::cout << "    Rayon cellule (m)   : " << radiusMeters << "\n";
  std::cout << "    Run                 : " << runNumber << "\n";
  std::cout << "  ---------------------------------------------------\n";
  std::cout << "    Trames MAC envoyees : " << (long) sent << "\n";
  std::cout << "    Trames MAC recues   : " << (long) received << "\n";
  std::cout << "    Taux de livraison   : "
            << std::fixed << std::setprecision (2) << (pdr * 100.0) << " %\n";
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
