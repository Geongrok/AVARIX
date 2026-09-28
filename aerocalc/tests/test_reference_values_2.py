import math
from aerocalc.modules import load_all
from aerocalc import core
load_all()

def run(cid, **o):
    s=core.get(cid); p={f["key"]:f["default"] for f in s["inputs"]}; p.update(o)
    return s["compute"](core.coerce_inputs(s,p)).to_dict()
def val(d,l,occ=0):
    hits=[r["value"] for g in d["groups"] for r in g["rows"] if r["label"]==l]
    if len(hits)>occ: return hits[occ]
    raise KeyError(l+" | have: "+", ".join(r["label"] for g in d["groups"] for r in g["rows"])[:700])
def chk(n,got,exp,tol):
    e=abs(got-exp)/abs(exp) if exp else abs(got)
    print(f"{'ok  ' if e<=tol else 'FAIL'} {n:54s} got {got:>13.7g}  exp {exp:>13.7g}  ({e:.1e})")

print("--- FLUID DYNAMICS ---")
# Colebrook-White solved implicitly. Independent fixed-point re-solve here.
d = run("pipe-flow", fluid="water20", rho=998.2, mu=0.001002, D=0.05, L=100.0,
        roughness="steel", eps=4.5e-5, known="Q", Q=0.004)
V = 0.004/(math.pi*0.05**2/4); Re = 998.2*V*0.05/0.001002
f = 0.02
for _ in range(200):   # independent Colebrook fixed point
    f = (-2*math.log10(4.5e-5/(3.7*0.05) + 2.51/(Re*math.sqrt(f))))**-2
chk("Reynolds number", val(d,"Reynolds number"), Re, 1e-9)
chk("mean velocity [m/s]", val(d,"Mean velocity"), V, 1e-9)
chk("Darcy friction factor (Colebrook)", val(d,"Darcy friction factor"), f, 1e-9)
chk("head loss [m]", val(d,"Major head loss"), f*(100/0.05)*V**2/(2*9.80665), 2e-3)

# Venturi: ISO 5167 incompressible
d = run("flow-meter", kind="venturi", D=0.1, d=0.05, dp=20000.0, rho=998.2,
        custom_cd=True, Cd=0.98)
beta=0.5; E=1/math.sqrt(1-beta**4)
Qexp = 0.98*E*(math.pi*0.05**2/4)*math.sqrt(2*20000/998.2)
chk("venturi volumetric flow [m3/s]", val(d,"Volumetric flow rate"), Qexp, 1e-9)
chk("beta ratio", val(d,"Diameter ratio"), 0.5, 1e-12)

# Plane Poiseuille: pure pressure-driven mean velocity = -h^2/(12 mu) dp/dx
d = run("couette-poiseuille", h=0.002, U=0.0, dpdx=-50000.0, mu=0.001002)
chk("Poiseuille mean velocity [m/s]", val(d,"Mean velocity"),
    50000*0.002**2/(12*0.001002), 1e-9)
chk("shear at stationary wall [Pa]", abs(val(d,"Shear stress at the stationary wall")), 50000*0.002/2, 1e-9)
chk("shear at moving wall [Pa]", abs(val(d,"Shear stress at the moving wall")), 50000*0.002/2, 1e-9)
chk("max velocity = 1.5 x mean", val(d,"Maximum velocity"), 1.5*val(d,"Mean velocity"), 1e-9)

print("--- THERMODYNAMICS ---")
# Ideal Brayton with real components
d = run("brayton-cycle", p1=101325.0, T1=288.15, rp=12.0, T3=1400.0,
        eta_c=1.0, eta_t=1.0, gamma=1.4, R=287.05287, regen=False)
tau = 12**(0.4/1.4)
chk("ideal Brayton efficiency [%]", val(d,"Thermal efficiency"), (1-1/tau)*100, 1e-9)
chk("compressor exit T2 [K]", val(d,"2 — actual compressor exit"), 288.15*tau, 1e-9)
chk("turbine exit T4 [K]", val(d,"4 — actual turbine exit"), 1400.0/tau, 1e-9)

d = run("piston-cycles", cycle="otto", rc=9.0, gamma=1.4)
chk("Otto efficiency rc=9 [%]", val(d,"Thermal efficiency"), (1-9**-0.4)*100, 1e-9)

# Isentropic compression of air
d = run("polytropic-process", process="isentropic", p1=1e5, T1=300.0,
        known="p2", value=1e6, gamma=1.4, R=287.05287, m=1.0)
chk("isentropic T2 [K]", val(d,"Temperature",1), 300*10**(0.4/1.4), 1e-9)
chk("isentropic p2 [Pa]", val(d,"Pressure",1), 1e6, 1e-12)
chk("entropy change ~ 0 [J/kg-K]", abs(val(d,"Change in entropy")), 0.0, 1e-9)

# Composite wall conduction + convection, series resistances
d = run("heat-transfer", geometry="wall", A=1.0, L1=0.1, k1=0.7, L2=0.05, k2=0.04,
        L3=0.0, k3=0.0, Th=350.0, Tc=280.0, h_in=25.0, h_out=10.0, radiation=False,
        fin=False)
Rtot = 1/25 + 0.1/0.7 + 0.05/0.04 + 1/10
chk("total thermal resistance [K/W]", val(d,"Total thermal resistance"), Rtot, 1e-9)
chk("heat transfer rate [W]", val(d,"Heat transfer rate"), 70/Rtot, 1e-9)
chk("overall U [W/m2K]", val(d,"Overall heat transfer coefficient"), 1/Rtot, 1e-9)

# Counterflow HX by effectiveness-NTU
d = run("heat-exchanger", arrangement="counter", U=500.0, A=10.0,
        m_hot=2.0, cp_hot=4182.0, T_hot_in=360.0,
        m_cold=3.0, cp_cold=4182.0, T_cold_in=290.0)
Cmin=2*4182; Cmax=3*4182; Cr=Cmin/Cmax; NTU=500*10/Cmin
eps=(1-math.exp(-NTU*(1-Cr)))/(1-Cr*math.exp(-NTU*(1-Cr)))
chk("NTU", val(d,"Number of transfer units"), NTU, 1e-9)
chk("effectiveness [%]", val(d,"Effectiveness"), eps*100, 1e-9)
chk("heat duty [kW]", val(d,"Heat transfer rate"), eps*Cmin*70/1000, 1e-9)
chk("LMTD cross-check vs e-NTU [kW]", val(d,"Heat transfer from LMTD method"), val(d,"Heat transfer rate"), 1e-6)

print("--- PROPULSION ---")
# Ideal rocket: c* and CF from closed form
g=1.2; R=8314.462618/22; Tc=3500.0; pc=7e6
d = run("rocket-nozzle", pc=pc, Tc=Tc, gamma=g, gas_spec="molar", Mw=22.0,
        expansion="area", eps=25.0, size_by="throat", At=0.02, pa=0.0, real=False)
cstar = math.sqrt(R*Tc/g)*((g+1)/2)**((g+1)/(2*(g-1)))
chk("characteristic velocity c* [m/s]", val(d,"Characteristic velocity"), cstar, 1e-9)
chk("throat temperature [K]", val(d,"Throat temperature"), Tc*2/(g+1), 1e-9)
chk("throat pressure [Pa]", val(d,"Throat pressure"), pc*(2/(g+1))**(g/(g-1)), 1e-9)
chk("mass flow [kg/s]", val(d,"Mass flow rate"), pc*0.02/cstar, 1e-9)
Isp=val(d,"Specific impulse"); CF=val(d,"Thrust coefficient")
chk("Isp = CF*c*/g0 consistency", Isp, CF*cstar/9.80665, 1e-9)

# Actuator disk in hover: vi = sqrt(T/2 rho A), P = T^1.5/sqrt(2 rho A)
d = run("propeller-momentum", T=5000.0, V=0.0, D=2.0, rho=1.225)
A=math.pi
chk("hover induced velocity [m/s]", val(d,"Induced velocity"),
    math.sqrt(5000/(2*1.225*A)), 1e-9)
chk("ideal hover power [kW]", val(d,"Ideal induced power"),
    5000**1.5/math.sqrt(2*1.225*A)/1000, 1e-9)
chk("disk loading [N/m2]", val(d,"Disk loading"), 5000/A, 1e-9)

print("--- FLIGHT MECHANICS ---")
W,S,CD0,AR,e = 50000.0,30.0,0.022,8.0,0.8
k = 1/(math.pi*AR*e)
d = run("level-flight", W=W,S=S,CD0=CD0,AR=AR,e=e,CLmax=1.6, altitude=0.0, engine="jet")
rho=1.225
chk("stall speed [m/s]", val(d,"Stall speed"), math.sqrt(2*W/(rho*S*1.6)), 2e-4)
chk("(L/D)max", val(d,"Maximum lift-to-drag ratio"), 1/(2*math.sqrt(CD0*k)), 1e-9)
chk("V_md [m/s]", val(d,"Minimum drag speed"),
    math.sqrt(2*W/(rho*S*math.sqrt(CD0/k))), 2e-4)
chk("V_mp = V_md/3^0.25", val(d,"Minimum power speed"),
    val(d,"Minimum drag speed")/3**0.25, 1e-9)
chk("minimum drag [N]", val(d,"Minimum drag"), W*2*math.sqrt(CD0*k), 1e-9)

# Level turn kinematics
d = run("turn-performance", W=W,S=S,CLmax=1.6,n_max=6.0,V=150.0,
        specify="bank", bank=60.0, altitude=5000.0)
n=1/math.cos(math.radians(60))
chk("load factor at 60 deg bank", val(d,"Load factor"), n, 1e-12)
chk("turn radius [m]", val(d,"Turn radius"), 150**2/(9.80665*math.sqrt(n*n-1)), 1e-9)
chk("turn rate [deg/s]", val(d,"Turn rate"),
    math.degrees(9.80665*math.sqrt(n*n-1)/150), 1e-9)

# Breguet jet endurance = (1/ct)(L/D)ln(W0/W1)
d = run("range-endurance", W0=60000.0, W_fuel=15000.0, S=30.0, CD0=0.022,
        AR=9.0, e=0.8, engine="jet", ct=2e-5, altitude=10000.0)
kk=1/(math.pi*9*0.8); LDmax=1/(2*math.sqrt(0.022*kk))
chk("max endurance [h]", val(d,"Maximum endurance"),
    (1/2e-5)*LDmax*math.log(60000/45000)/3600, 1e-9)
