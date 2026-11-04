/*
 * stopmnt-propagation.h
 *
 * Modeles de propagation partages par les deux familles du projet STOP-MNT,
 * LoRaWAN (lorawan-cell-shadow.cc) et cellulaire (lte-cell.cc), pour que la
 * comparaison se fasse sur les memes bases : meme ombrage par lien, meme
 * correlation spatiale, meme terme de vegetation, meme borne d'horizon.
 *
 * Copier ce fichier dans ~/ns-3.48/scratch/ a cote des .cc qui l'incluent.
 */
#ifndef STOPMNT_PROPAGATION_H
#define STOPMNT_PROPAGATION_H

#include "ns3/core-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/propagation-module.h"

#include <cmath>
#include <map>
#include <utility>
#include <vector>

namespace ns3
{

// =============================================================================
// Modele d'ombrage maison.
//
// Il se branche derriere un autre modele de perte (ici le log-distance) grace
// au chainage natif de ns-3 : le log-distance calcule la puissance moyenne
// recue, puis ce modele retranche un tirage d'ombrage en dB.
//
// Le tirage suit une loi normale de moyenne 0 et d'ecart-type sigma.
//
// Il est memorise PAR LIEN noeud-passerelle : cle = (identifiant du noeud,
// indice de la passerelle). Consequences voulues :
//   - un meme lien garde toujours le meme ombrage (le noeud mal loti le reste) ;
//   - deux passerelles voient le meme noeud avec des ombrages independants,
//     condition de la diversite de reception (hypothese optimiste : en realite
//     les ombrages de deux liens d'un meme noeud sont partiellement correles) ;
//   - la liaison descendante (acquittement) reprend l'ombrage de la montante
//     du meme lien : reciprocite.
// Les liens noeud-noeud ne recoivent pas d'ombrage (sans effet en LoRaWAN, les
// noeuds n'ecoutent pas les montantes des autres).
// Si aucune position de passerelle n'est declaree, on revient au comportement
// d'origine : tirage indexe sur la position de l'emetteur.
//
// Correlation spatiale (mobilite) : modele de Gudmundson, tel qu'implemente
// dans ns-3 (ThreeGppPropagationLossModel::GetShadowing). Quand le noeud s'est
// deplace de D depuis le dernier calcul sur ce lien :
//   R = exp(-D / dcor),  nouveau = R x ancien + racine(1 - R^2) x sigma x N(0,1).
// Un noeud fixe (D = 0) garde son tirage. dcor vient du config par zone
// (3GPP TR 38.901, tableau 7.5-6). dcor = 0 : tirage independant a chaque
// deplacement (pas de correlation).
// =============================================================================
class NodeShadowingLossModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid =
        TypeId ("ns3::NodeShadowingLossModel")
            .SetParent<PropagationLossModel> ()
            .SetGroupName ("StopMnt")
            .AddConstructor<NodeShadowingLossModel> ();
    return tid;
  }

  NodeShadowingLossModel ()
  {
    m_normal = CreateObject<NormalRandomVariable> ();
    m_normal->SetAttribute ("Mean", DoubleValue (0.0));
    SetSigma (0.0);
  }

  // sigma en dB. La loi normale travaille en variance, soit sigma au carre.
  void SetSigma (double sigmaDb)
  {
    m_sigma = sigmaDb;
    m_normal->SetAttribute ("Variance", DoubleValue (sigmaDb * sigmaDb));
  }

  // Positions des passerelles, pour reconnaitre l'extremite passerelle d'un lien.
  void SetGatewayPositions (const std::vector<Vector> &gws)
  {
    m_gwPositions = gws;
  }

  // Distance de decorrelation en metres (Gudmundson). 0 = pas de correlation.
  void SetCorrelationDistance (double dcorM)
  {
    m_dcor = dcorM;
  }

  // Correlation de l'ombrage entre les liens d'un meme noeud vers des sites
  // differents (3GPP : 0,5 entre sites, TR 36.942 cite par TR 36.825, 36.826,
  // 36.809). Ombrage d'un lien = racine(rho) x composante commune au noeud
  // + racine(1 - rho) x composante propre au lien. rho = 0 : liens independants
  // (comportement d'origine, memes tirages).
  void SetSiteCorrelation (double rho)
  {
    m_rho = rho;
  }

private:
  double DoCalcRxPower (double txPowerDbm,
                        Ptr<MobilityModel> a,
                        Ptr<MobilityModel> b) const override
  {
    if (m_sigma <= 0.0)
      {
        return txPowerDbm;
      }
    Vector p;
    int gwIndex = -1;
    if (m_gwPositions.empty ())
      {
        p = a->GetPosition ();   // comportement d'origine : indexe sur l'emetteur
      }
    else
      {
        int ia = GatewayIndex (a->GetPosition ());
        int ib = GatewayIndex (b->GetPosition ());
        if (ia >= 0 && ib < 0)
          {
            gwIndex = ia;
            p = b->GetPosition ();
          }
        else if (ib >= 0 && ia < 0)
          {
            gwIndex = ib;
            p = a->GetPosition ();
          }
        else
          {
            return txPowerDbm;   // lien noeud-noeud (ou passerelle-passerelle)
          }
      }
    // Cle du lien : identifiant du noeud cote non-passerelle (a defaut, sa
    // position arrondie), et indice de la passerelle.
    Ptr<MobilityModel> edMob = (gwIndex >= 0 && GatewayIndex (a->GetPosition ()) == gwIndex) ? b : a;
    Ptr<Node> edNode = edMob->GetObject<Node> ();
    long id = edNode ? static_cast<long> (edNode->GetId ())
                     : (std::lround (p.x) * 1000003L + std::lround (p.y));
    double shadowDb = Component (std::make_pair (id, gwIndex), p);
    if (m_rho > 0.0 && gwIndex >= 0)
      {
        // Composante commune au noeud (cle de passerelle -2), meme loi.
        double common = Component (std::make_pair (id, -2), p);
        shadowDb = std::sqrt (m_rho) * common + std::sqrt (1.0 - m_rho) * shadowDb;
      }
    // Un ombrage positif est une perte supplementaire : il abaisse la puissance.
    return txPowerDbm - shadowDb;
  }

  int64_t DoAssignStreams (int64_t stream) override
  {
    m_normal->SetStream (stream);
    return 1;
  }

  // Composante d'ombrage (sigma inclus) pour une cle, avec mise a jour de
  // Gudmundson si le noeud a bouge depuis le dernier calcul.
  double Component (const std::pair<long, int> &key, const Vector &p) const
  {
    auto it = m_shadowing.find (key);
    if (it == m_shadowing.end ())
      {
        double v = m_normal->GetValue ();
        m_shadowing[key] = std::make_pair (v, p);
        return v;
      }
    double moved = std::hypot (p.x - it->second.second.x, p.y - it->second.second.y);
    if (moved < 1e-6)
      {
        return it->second.first;
      }
    double r = (m_dcor > 0.0) ? std::exp (-moved / m_dcor) : 0.0;
    double v = r * it->second.first + std::sqrt (1.0 - r * r) * m_normal->GetValue ();
    it->second = std::make_pair (v, p);
    return v;
  }

  // Indice de la passerelle situee a cette position (a moins d'un metre), ou -1.
  int GatewayIndex (const Vector &q) const
  {
    for (size_t i = 0; i < m_gwPositions.size (); ++i)
      {
        if (std::hypot (q.x - m_gwPositions[i].x, q.y - m_gwPositions[i].y) < 1.0 &&
            std::abs (q.z - m_gwPositions[i].z) < 1.0)
          {
            return static_cast<int> (i);
          }
      }
    return -1;
  }

  Ptr<NormalRandomVariable> m_normal;
  double m_sigma;
  std::vector<Vector> m_gwPositions;
  double m_dcor = 0.0;
  double m_rho = 0.0;
  // (noeud, passerelle) -> (ombrage en dB, position du noeud au dernier calcul)
  mutable std::map<std::pair<long, int>, std::pair<double, Vector>> m_shadowing;
};

// =============================================================================
// Perte constante en exces, par exemple la vegetation UIT-R P.833 (rural
// arbore). Maillon de la chaine qui retranche une valeur fixe en dB, calculee
// par l'orchestrateur a partir du config. 0 = maillon non accroche.
// =============================================================================
class ExcessLossModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid =
        TypeId ("ns3::ExcessLossModel")
            .SetParent<PropagationLossModel> ()
            .SetGroupName ("StopMnt")
            .AddConstructor<ExcessLossModel> ();
    return tid;
  }

  void SetLoss (double lossDb)
  {
    m_loss = lossDb;
  }

private:
  double DoCalcRxPower (double txPowerDbm, Ptr<MobilityModel> a,
                        Ptr<MobilityModel> b) const override
  {
    return txPowerDbm - m_loss;
  }

  int64_t DoAssignStreams (int64_t stream) override
  {
    return 0;
  }

  double m_loss = 0.0;
};

NS_OBJECT_ENSURE_REGISTERED (ExcessLossModel);

// =============================================================================
// Vegetation dependante de la distance, comptee une seule fois.
//
//   A(d) = Am [1 - exp(-A0(d) / Am)],   A0(d) = c f^a d^b
//
// A0 est la croissance du modele ITU ancien (CCIR 1986, c = 0,2, a = 0,3,
// b = 0,6, f en MHz, d en m, valable sous 400 m) ; Am est la saturation de
// l'UIT-R P.833-10 § 2.1 (Am = A1 f^alpha), multipliee par la densite. Pour
// une petite profondeur A ~ A0, pour une grande A -> Am. Toutes les valeurs
// viennent du config via la ligne de commande.
// =============================================================================
class VegetationLossModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid =
        TypeId ("ns3::VegetationLossModel")
            .SetParent<PropagationLossModel> ()
            .SetGroupName ("StopMnt")
            .AddConstructor<VegetationLossModel> ();
    return tid;
  }

  void Set (double amDb, double coef, double fMHz, double fExp, double dExp)
  {
    m_am = amDb;
    m_growthAtUnitDist = coef * std::pow (fMHz, fExp);
    m_dExp = dExp;
  }

  double Loss (double dMeters) const
  {
    if (m_am <= 0.0 || dMeters <= 0.0)
      {
        return 0.0;
      }
    double a0 = m_growthAtUnitDist * std::pow (dMeters, m_dExp);
    return m_am * (1.0 - std::exp (-a0 / m_am));
  }

private:
  double DoCalcRxPower (double txPowerDbm, Ptr<MobilityModel> a,
                        Ptr<MobilityModel> b) const override
  {
    Vector pa = a->GetPosition ();
    Vector pb = b->GetPosition ();
    return txPowerDbm - Loss (std::hypot (pa.x - pb.x, pa.y - pb.y));
  }

  int64_t DoAssignStreams (int64_t stream) override
  {
    return 0;
  }

  double m_am = 0.0;
  double m_growthAtUnitDist = 0.0;
  double m_dExp = 0.6;
};

NS_OBJECT_ENSURE_REGISTERED (VegetationLossModel);

// =============================================================================
// Gain d'antenne de la passerelle, en reception seulement.
//
// Ajoute gainDb a la puissance recue quand le recepteur est une passerelle
// (position egale a l'une des passerelles). Les descendantes (passerelle vers
// noeud) n'en profitent pas : la puissance rayonnee d'une passerelle est
// plafonnee par la reglementation, gain d'antenne compris.
// =============================================================================
class GatewayRxGainModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid =
        TypeId ("ns3::GatewayRxGainModel")
            .SetParent<PropagationLossModel> ()
            .SetGroupName ("StopMnt")
            .AddConstructor<GatewayRxGainModel> ();
    return tid;
  }

  void Set (const std::vector<Vector> &gws, double gainDb)
  {
    m_gws = gws;
    m_gain = gainDb;
  }

private:
  double DoCalcRxPower (double txPowerDbm, Ptr<MobilityModel> a,
                        Ptr<MobilityModel> b) const override
  {
    Vector pb = b->GetPosition ();
    for (const Vector &g : m_gws)
      {
        if (std::abs (pb.x - g.x) < 0.01 && std::abs (pb.y - g.y) < 0.01 && std::abs (pb.z - g.z) < 0.01)
          {
            return txPowerDbm + m_gain;
          }
      }
    return txPowerDbm;
  }

  int64_t DoAssignStreams (int64_t stream) override
  {
    return 0;
  }

  std::vector<Vector> m_gws;
  double m_gain = 0.0;
};

NS_OBJECT_ENSURE_REGISTERED (GatewayRxGainModel);

NS_OBJECT_ENSURE_REGISTERED (NodeShadowingLossModel);

// =============================================================================
// Borne d'horizon radio.
//
// Dernier maillon de la chaine de perte. Le modele log-distance a une pente
// n'a pas de limite physique : avec un exposant faible (lacustre, n = 2), il
// prolonge l'espace libre a des centaines de km. Ce maillon ajoute un plafond :
// au-dela de l'horizon radio, pas de reception.
//
//   d_horizon_km = coef * (sqrt(h_passerelle_m) + sqrt(h_noeud_m))
//   coef = 4,12 pour la refraction standard, Terre de rayon effectif 4/3.
//
// Le calcul de d_horizon se fait dans main a partir des parametres recus.
// Ici, si la distance horizontale entre emetteur et recepteur depasse
// d_horizon, on retranche une perte sentinelle qui rend la trame non recevable.
// En dessous, le maillon est transparent.
// =============================================================================
class RadioHorizonLossModel : public PropagationLossModel
{
public:
  static TypeId GetTypeId (void)
  {
    static TypeId tid =
        TypeId ("ns3::RadioHorizonLossModel")
            .SetParent<PropagationLossModel> ()
            .SetGroupName ("StopMnt")
            .AddConstructor<RadioHorizonLossModel> ();
    return tid;
  }

  void SetHorizon (double horizonMeters, double lossBeyondDb)
  {
    m_horizon = horizonMeters;
    m_lossBeyond = lossBeyondDb;
  }

private:
  double DoCalcRxPower (double txPowerDbm,
                        Ptr<MobilityModel> a,
                        Ptr<MobilityModel> b) const override
  {
    Vector pa = a->GetPosition ();
    Vector pb = b->GetPosition ();
    double d = std::hypot (pa.x - pb.x, pa.y - pb.y);
    return (d > m_horizon) ? (txPowerDbm - m_lossBeyond) : txPowerDbm;
  }

  int64_t DoAssignStreams (int64_t stream) override
  {
    return 0;
  }

  double m_horizon = 0.0;
  double m_lossBeyond = 0.0;
};

NS_OBJECT_ENSURE_REGISTERED (RadioHorizonLossModel);

} // namespace ns3

#endif // STOPMNT_PROPAGATION_H
