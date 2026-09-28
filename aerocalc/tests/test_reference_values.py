import math
from aerocalc.modules import load_all
from aerocalc import core
load_all()

def run(cid, **over):
    spec = core.get(cid)
    p = {f["key"]: f["default"] for f in spec["inputs"]}
    p.update(over)
    return spec["compute"](core.coerce_inputs(spec, p)).to_dict()

def val(d, label):
    for g in d["groups"]:
        for r in g["rows"]:
            if r["label"] == label:
                return r["value"]
    raise KeyError(label)

def chk(name, got, exp, tol):
    err = abs(got-exp)/abs(exp) if exp else abs(got)
    flag = "ok  " if err <= tol else "FAIL"
    print(f"{flag} {name:52s} got {got:>14.7g}  exp {exp:>13.7g}  ({err:.2e})")

print("--- SPACE ---")
d = run("orbital-elements", spec="alt", hp=400, ha=400)
chk("LEO 400 km period [min]", val(d,"Orbital period"), 92.5586, 1e-4)
chk("LEO 400 km v_p [km/s]",   val(d,"Velocity at periapsis"), 7.668586, 1e-5)
chk("GEO radius [km]",         val(d,"Geostationary radius"), 42164.17, 1e-5)

d = run("orbital-elements", spec="radii", rp=6678, ra=42164, j2_rates=True, i=0)
chk("GTO period [min]", val(d,"Orbital period"),
    2*math.pi*math.sqrt(((6678+42164)/2*1e3)**3/3.986004418e14)/60, 1e-9)

d = run("orbit-transfer", spec="r", r1=6678, r2=42164)
chk("Hohmann LEO->GEO dv1 [km/s]", val(d,"First burn"),  2.4257686, 1e-4)
chk("Hohmann LEO->GEO dv2 [km/s]", val(d,"Second burn"), 1.4668389, 1e-4)
chk("Hohmann LEO->GEO total",      val(d,"Total \u0394v"), 3.892969, 1e-4)
chk("Hohmann transfer time [h]",   val(d,"Transfer time"), 5.275014, 1e-3)

d = run("groundtrack-coverage", h=700, e=0, i=98.186)
chk("Sun-sync i at 700 km [deg]", val(d,"Sun-synchronous inclination at this altitude"), 98.186, 3e-4)
chk("Node rate sun-sync [deg/day]", val(d,"Nodal regression"), 0.9856, 3e-3)

d = run("escape-hyperbolic", h_park=200, mode="c3", C3=0)
chk("Escape velocity 200 km [km/s]", val(d,"Escape velocity"), 11.0086, 1e-4)
chk("dv simple escape [km/s]", val(d,"\u0394v for simple escape"), 3.2246, 1e-3)

d = run("kepler-propagation", a=26600, e=0.74, known="nu", nu=180.0)
chk("Molniya apoapsis r [km]", val(d,"Radius"), 26600*1.74, 1e-9)
chk("Molniya t at apoapsis [min]", val(d,"Time from periapsis"),
    math.pi*math.sqrt((26600e3)**3/3.986004418e14)/60, 1e-9)

d = run("rocket-equation", stages=1, payload=0, isp1=300, mp1=9000, ms1=1000)
chk("Tsiolkovsky dv [km/s]", val(d,"Total \u0394v"), 300*9.80665*math.log(10)/1000, 1e-9)

print("--- AVIONICS ---")
d = run("link-budget", freq=12, range=36000, tx_spec="gain", Gt=40, rx_spec="dia", Dr=2.4, eta_r=0.6)
chk("FSPL 12 GHz 36000 km [dB]", val(d,"Free space path loss"),
    20*math.log10(4*math.pi*36e6/(299792458/12e9)), 1e-12)
chk("Rx gain 2.4 m dish [dBi]", val(d,"Receive antenna gain"),
    10*math.log10(0.6*(math.pi*2.4/(299792458/12e9))**2), 1e-12)

d = run("antenna", kind="dish", D=2.4, freq=12, eta=0.6)
chk("Dish gain [dBi]", val(d,"Gain"), 47.372, 1e-4)
chk("Dish HPBW [deg]", val(d,"Half-power beamwidth"), 70*0.0249827/2.4, 1e-6)
chk("Far field 2D^2/lam [m]", val(d,"Far-field distance"), 2*2.4**2/0.0249827, 1e-6)

d = run("control-response", spec="params", wn=10, zeta=0.7)
chk("Overshoot at z=0.7 [%]", val(d,"Overshoot"),
    100*math.exp(-math.pi*0.7/math.sqrt(1-0.49)), 1e-9)
chk("Settling 2% [s]", val(d,"Settling time (2 %)"), 4/(0.7*10), 1e-9)
d = run("control-response", spec="perf", Mp=5, ts=2)
chk("Inverse design -> overshoot [%]", val(d,"Overshoot"), 5.0, 1e-6)
chk("Inverse design -> settling [s]", val(d,"Settling time (2 %)"), 2.0, 1e-6)

d = run("filter-design", kind="butter", order=4, fc=1000, fs_stop=3000, A_stop=40)
chk("Butterworth n=4 at 3fc [dB]", val(d,"Attenuation at the stopband edge"),
    10*math.log10(1+3**8), 1e-9)
chk("Butterworth roll-off [dB/dec]", val(d,"Ultimate roll-off rate"), 80, 1e-12)

d = run("noise-cascade", n_stages=2, T_ant=0, g1=20, nf1=1.0, g2=10, nf2=10.0)
F = 10**0.1 + (10**1.0-1)/100
chk("Friis cascade NF [dB]", val(d,"Total noise figure"), 10*math.log10(F), 1e-9)
chk("Cascade Te [K]", val(d,"Equivalent noise temperature"), (F-1)*290, 1e-9)

print("--- STRUCTURES ---")
d = run("beam-bending", section="rect", b=0.05, h=0.1, material="al2024",
        case="cant_point", L=2.0, P=5000)
I = 0.05*0.1**3/12
chk("Cantilever sigma_max [MPa]", val(d,"Maximum bending stress"), 5000*2*0.05/I/1e6, 1e-9)
chk("Cantilever delta [mm]", val(d,"Maximum deflection"), 5000*8/(3*73.1e9*I)*1000, 1e-9)

d = run("column-buckling", section="rect", b=0.05, h=0.1, L=1.0, ends="pinned",
        material="al2024", P=50000)
Imin = 0.05**3*0.1/12
chk("Euler P_cr [kN]", val(d,"Euler load (regardless of regime)"),
    math.pi**2*73.1e9*min(I,Imin)/1.0**2/1000, 2e-3)

d = run("pressure-vessel", shape="cylinder", r=0.5, t=0.005, p=2e6, material="al2024")
chk("Hoop stress [MPa]", val(d,"Hoop (circumferential) stress"), 200.0, 1e-9)
chk("Longitudinal stress [MPa]", val(d,"Longitudinal (axial) stress"), 100.0, 1e-9)
chk("von Mises [MPa]", val(d,"von Mises stress"),
    math.sqrt(0.5*((200-100)**2+(100+2)**2+(-2-200)**2)), 1e-9)

d = run("stress-transformation", sx=100, sy=-40, txy=50, triaxial=False)
chk("Principal s1 [MPa]", val(d,"Maximum principal stress"), 30+math.sqrt(70**2+50**2), 1e-9)
chk("Principal s2 [MPa]", val(d,"Minimum principal stress"), 30-math.sqrt(70**2+50**2), 1e-9)
chk("tau_max [MPa]", val(d,"Maximum in-plane shear stress"), math.sqrt(70**2+50**2), 1e-9)

d = run("torsion", kind="solid", d=0.05, L=1.0, T=1000, material="al2024")
J = math.pi*0.05**4/32
chk("Torsion tau_max [MPa]", val(d,"Maximum shear stress"), 1000*0.025/J/1e6, 1e-9)
G = 73.1e9/(2*1.33)
chk("Angle of twist [deg]", val(d,"Angle of twist"), math.degrees(1000*1/(G*J)), 1e-9)

print("--- CLT quasi-isotropy self-test ---")
d = run("laminate-clt", ply="cfrp_hs", layup="0/45/-45/90", symmetric=True,
        t_ply=0.125, apply_load=False)
Ex = val(d,"Longitudinal modulus"); Ey = val(d,"Transverse modulus")
Gxy = val(d,"Shear modulus"); nu = val(d,"Major Poisson's ratio")
chk("quasi-iso Ex == Ey", Ex, Ey, 1e-9)
chk("quasi-iso G == E/(2(1+nu))", Gxy, Ex/(2*(1+nu)), 1e-9)
print(f"     [{'/'.join(['0','45','-45','90'])}]s AS4/3501-6:  Ex={Ex:.4g} GPa  nu={nu:.4f}")
