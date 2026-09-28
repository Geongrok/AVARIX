(() => {
  const form = document.getElementById("auth-form");
  const signin = document.getElementById("signin-tab");
  const signup = document.getElementById("signup-tab");
  const nameField = document.getElementById("name-field");
  const confirmField = document.getElementById("confirm-field");
  const forgot = document.getElementById("forgot");
  const passwordHint = document.getElementById("password-hint");
  const password = document.getElementById("password");
  const notice = document.getElementById("notice");
  let mode = "signin";
  function setMode(next) {
    mode=next; const creating=mode==="signup";
    signin.classList.toggle("active",!creating); signup.classList.toggle("active",creating);
    signin.setAttribute("aria-selected",String(!creating)); signup.setAttribute("aria-selected",String(creating));
    nameField.hidden=!creating; confirmField.hidden=!creating; forgot.hidden=creating; passwordHint.hidden=!creating;
    password.autocomplete=creating?"new-password":"current-password";
    document.getElementById("form-title").textContent=creating?"Create your account":"Sign in to your account";
    document.getElementById("form-subtitle").textContent=creating?"Join the KCG College aerospace community.":"Continue your aerospace research.";
    document.getElementById("submit-label").textContent=creating?"Create account":"Sign in";
    notice.hidden=true;
  }
  function showNotice(message,error=false){notice.textContent=message;notice.classList.toggle("error",error);notice.hidden=false;}
  signin.addEventListener("click",()=>setMode("signin")); signup.addEventListener("click",()=>setMode("signup"));
  document.getElementById("toggle-password").addEventListener("click",e=>{
    const visible=password.type==="password"; password.type=visible?"text":"password";
    e.currentTarget.textContent=visible?"Hide":"Show"; e.currentTarget.setAttribute("aria-label",visible?"Hide password":"Show password");
  });
  forgot.addEventListener("click",()=>showNotice("Password recovery is not configured yet. Please contact the AVARIX administrator."));
  form.addEventListener("submit",async e=>{
    e.preventDefault();
    const email=document.getElementById("email").value.trim().toLowerCase();
    const name=document.getElementById("full-name").value.trim();
    const confirm=document.getElementById("confirm-password").value;
    if(!/^[^\s@]+@kcgcollege\.com$/i.test(email)){showNotice("Please use a valid @kcgcollege.com email address.",true);return;}
    if(!password.value||(mode==="signup"&&password.value.length<8)){showNotice(mode==="signup"?"Password must contain at least 8 characters.":"Enter your password.",true);return;}
    if(mode==="signup"&&!name){showNotice("Please enter your full name.",true);return;}
    if(mode==="signup"&&password.value!==confirm){showNotice("The passwords do not match.",true);return;}
    const button=form.querySelector(".submit"); button.disabled=true;
    showNotice(mode==="signup"?"Creating your account…":"Signing you in…");
    try{
      const response=await fetch(mode==="signup"?"/api/auth/signup":"/api/auth/login",{
        method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
        body:JSON.stringify(mode==="signup"?{name,email,password:password.value}:{email,password:password.value})
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.detail||"Authentication failed. Please try again.");
      window.location.replace("/app");
    }catch(error){showNotice(error.message||"Unable to connect to AVARIX. Please try again.",true);}
    finally{button.disabled=false;}
  });
  setMode("signin");
})();
