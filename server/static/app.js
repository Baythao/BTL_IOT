'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const permissionNames = {view_status:'Xem trạng thái',view_thresholds:'Xem ngưỡng',view_history:'Xem lịch sử'};
const pages = {
  overview:['Tổng quan hệ thống','Dữ liệu cảm biến và đầu ra được báo về từ ESP32.','view_status'],
  thresholds:['Ngưỡng cảnh báo','Các giá trị cấu hình thực tế do thiết bị gửi lên.','view_thresholds'],
  history:['Lịch sử hoạt động','Theo dõi cảnh báo và các thay đổi đã ghi nhận.','view_history'],
  users:['Người dùng & phân quyền','Quản lý ai được truy cập và những gì họ được xem.','admin'],
  audit:['Nhật ký quản trị','Các thay đổi tài khoản được ghi lại để đối chiếu.','admin'],
  account:['Tài khoản của bạn','Thông tin truy cập và bảo mật tài khoản.',null]
};
let user=null, csrf='', page='overview', users=[], historyData=null, historyTab='events', busy=false;
let toastTimer;

function toast(text,error=false){
  clearTimeout(toastTimer);
  $('#toast').textContent=text;
  $('#toast').classList.toggle('error-toast',error);
  $('#toast').hidden=false;
  toastTimer=setTimeout(()=>$('#toast').hidden=true,5000);
}
function stamp(ts){return ts?new Date(ts*1000).toLocaleString('vi-VN'):'Chưa có dữ liệu';}
function badge(text,kind='neutral'){return `<span class="badge ${kind}">${esc(text)}</span>`;}
function allowed(p){
  const permission=pages[p][2];
  return user && (!permission || user.role==='admin' || user.permissions.includes(permission));
}
function firstPage(){return Object.keys(pages).find(p=>allowed(p)) || 'account';}

async function api(path,method='GET',body){
  const opts={method,headers:{},cache:'no-store',credentials:'same-origin'};
  if(method!=='GET'){
    opts.headers['X-CSRF-Token']=csrf;
    if(method!=='DELETE'){
      opts.headers['Content-Type']='application/json';
      opts.body=JSON.stringify(body??{});
    }
  }
  let response;
  try{
    response=await fetch(path,opts);
  }catch{
    throw new Error('Không kết nối được máy chủ. Kiểm tra mạng và chương trình web trên laptop.');
  }
  const data=await response.json().catch(()=>({error:'Máy chủ trả về dữ liệu không hợp lệ.'}));
  if(!response.ok){
    if(response.status===401 && path!=='/api/login') showLogin();
    throw new Error(data.error||'Không thể thực hiện yêu cầu.');
  }
  return data;
}

function showLogin(){
  user=null;
  $('#app-screen').hidden=true;
  $('#login-screen').hidden=false;
  $$('dialog[open]').forEach(d=>d.close());
}

function paintUser(){
  $('#login-screen').hidden=true;
  $('#app-screen').hidden=false;
  $('#profile-name').textContent=user.full_name;
  $('#profile-role').textContent=user.role==='admin'?'Quản trị viên':'Người dùng';
  $('#avatar').textContent=user.full_name.slice(0,1).toUpperCase();
  $$('#nav button').forEach(b=>b.hidden=!allowed(b.dataset.page)||(user.must_change && b.dataset.page!=='account'));
  $('#force-password').hidden=!user.must_change;
  $('#account-summary').innerHTML=`<div class="account-line"><small>Họ tên</small>${esc(user.full_name)}</div><div class="account-line"><small>Tên đăng nhập</small>${esc(user.username)}</div><div class="account-line"><small>Vai trò</small>${badge(user.role==='admin'?'Admin':'Người dùng',user.role==='admin'?'good':'neutral')}</div><div class="account-line"><small>Quyền truy cập</small>${user.permissions.map(p=>badge(permissionNames[p])).join(' ')||'Chưa có quyền giám sát'}</div>`;
}

async function refreshSession(){
  const s=await api('/api/session');
  csrf=s.csrf;
  user=s.user;
  $('#device-label').textContent=s.device;
  if(!user){showLogin();return false;}
  paintUser();
  return true;
}

async function navigate(target){
  if(!user)return;
  page=user.must_change?'account':allowed(target)?target:firstPage();
  $$('.page').forEach(el=>el.hidden=el.id!==`page-${page}`);
  $$('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  $('#page-title').textContent=pages[page][0];
  $('#page-crumb').textContent=pages[page][0];
  $('#page-description').textContent=pages[page][1];
  try{await loadPage();}catch(e){toast(e.message,true);}
}

function empty(message){return `<div class="empty">${esc(message)}</div>`;}
function doorIsOpen(d){return Number(d?.servo)>=45;}

function paintOverview(s){
  const d=s.data;
  $('#connection-badge').className=`badge ${s.fresh?'good':'warn'}`;
  $('#connection-badge').textContent=s.fresh?'● Đang nhận dữ liệu':s.connection==='offline'?'● Thiết bị mất kết nối':'● Chưa có dữ liệu mới';
  $('#last-seen').textContent=s.last_seen?`Lần nhận cuối: ${stamp(s.last_seen)}`:'Đang chờ ESP32 gửi trạng thái';
  $('#stale-warning').hidden=!d||s.fresh;
  $('#stale-warning').textContent='Dữ liệu đã cũ. Các trạng thái bên dưới là lần ghi nhận cuối, chưa thể xác nhận tình trạng hiện tại.';

  // Chỉ hiện hai dòng trạng thái này khi dữ liệu xác nhận có lửa.
  const coLua=Boolean(d && d.fire===true);
  $('#fire-value').hidden=!coLua;
  $('#fire-value').textContent=coLua?'Có tín hiệu lửa':'';
  $('#fire-value').classList.toggle('danger-text',coLua);
  $('#fire-detail').hidden=!coLua;
  $('#fire-detail').textContent=coLua
    ?(s.fresh?'Theo tín hiệu cảm biến':'Trạng thái lần nhận cuối')
    :'';

  $('#gas-value').textContent=d?d.gas_adc.toLocaleString('vi-VN'):'—';
  $('#gas-detail').textContent=d?(!d.gas_ready?'Đang chờ cảm biến gas':d.gas?'Vượt ngưỡng cảnh báo':'Dưới ngưỡng kích hoạt'):'Giá trị ADC, không phải ppm';
  $('#gas-value').classList.toggle('danger-text',!!d?.gas);
  $('#outputs-value').textContent=d?`${Number(d.fan)+Number(d.pump)+Number(d.buzzer)} / 3`:'—';

  const open=doorIsOpen(d);
  $('#servo-value').textContent=d?(open?'Mở':'Đóng'):'—';

  const hardware=[
    ['fan','Quạt hút','GPIO18','✣'],
    ['pump','Máy bơm','GPIO21','◉'],
    ['buzzer','Còi cảnh báo','GPIO13','♬'],
    ['servo','Cửa tự động','GPIO23 · 2 servo','🚪']
  ];

  $('#hardware-list').innerHTML=hardware.map(([key,name,pin,icon])=>
    `<div class="hardware-row">
      <span class="hardware-symbol">${icon}</span>
      <div class="hardware-name"><strong>${name}</strong><small>${pin}</small></div>
      ${badge(
        !d?'Chưa có dữ liệu':key==='servo'?(open?'Mở':'Đóng'):d[key]?'Đang kích':'Tắt',
        !d||!s.fresh?'neutral':key==='servo'?(open?'good':'neutral'):(d[key]?'good':'neutral')
      )}
    </div>`
  ).join('');

  $('#gas-number').textContent=d?d.gas_adc.toLocaleString('vi-VN'):'—';
  $('#gas-meter').value=d?d.gas_adc:0;
  $('#gas-summary').textContent=!d
    ?'Chưa có mẫu đo.'
    :!s.fresh
      ?'Mẫu đo cuối đã cũ — cần kiểm tra kết nối.'
      :!d.gas_ready
        ?'Thiết bị đang chờ trước khi xét ngưỡng gas.'
        :d.gas
          ?'Gas vượt ngưỡng thử nghiệm. Hãy kiểm tra khu vực.'
          :'Chưa có cảnh báo gas theo ngưỡng đang cấu hình.';
}

function paintThresholds(s){
  $('#threshold-time').textContent=s.last_seen
    ?`Nhận lúc ${stamp(s.last_seen)}${s.fresh?'':' · Dữ liệu đã cũ'}`
    :'Chưa nhận được cấu hình từ thiết bị';

  if(!s.config){
    $('#threshold-content').innerHTML=empty('ESP32 chưa gửi thông số ngưỡng. Hãy nạp bản firmware trong bộ code mới.');
    return;
  }

  const c=s.config;
  const entries=[
    ['Ngưỡng bật cảnh báo gas',`${c.gas_on} ADC`,'Kích cảnh báo khi giá trị bằng hoặc vượt ngưỡng.'],
    ['Ngưỡng tắt cảnh báo gas',`${c.gas_off} ADC`,'Xóa cảnh báo gas khi giá trị bằng hoặc dưới ngưỡng.'],
    ['Thời gian chờ gas',`${c.gas_warmup_ms/1000} giây`,'Thời gian bỏ qua ban đầu; không chứng minh cảm biến đã ổn định.'],
    ['Chu trình lửa tối đa',`${c.fire_run_ms/1000} giây`,'Giới hạn thời gian kích bơm và cửa của mô hình.'],
    ['Mức phát hiện lửa',c.fire_active_level?'HIGH (1)':'LOW (0)','Phải phù hợp tín hiệu DO của module thực tế.']
  ];

  $('#threshold-content').innerHTML=
    `<div class="threshold-grid">${entries.map(([a,b,c])=>
      `<div class="threshold-item"><small>${a}</small><strong>${esc(b)}</strong><p>${c}</p></div>`
    ).join('')}</div>`;
}

const deliveryNames={
  pending:'Chờ gửi',
  sending:'Đang gửi',
  dry_run:'Chạy thử',
  accepted:'Dịch vụ đã nhận',
  failed:'Lỗi gửi',
  uncertain:'Chưa rõ kết quả'
};
const componentNames={
  fire:'Cảm biến lửa',
  gas:'Cảnh báo gas',
  fan:'Quạt hút',
  pump:'Máy bơm',
  buzzer:'Còi',
  servo:'Cửa tự động'
};

function componentValue(key,value){
  if(value===null)return 'Mẫu đầu / sau gián đoạn';
  const v=JSON.parse(value);
  return key==='servo'
    ?(Number(v)>=45?'Mở cửa':'Đóng cửa')
    :v?'Bật / Có tín hiệu':'Tắt / Không có tín hiệu';
}

function paintHistory(){
  if(!historyData)return;
  $$('.tab').forEach(b=>b.classList.toggle('active',b.dataset.history===historyTab));
  $('#history-title').textContent=historyTab==='events'?'Lịch sử cảnh báo':'Thay đổi phần cứng';

  if(historyTab==='events'){
    const rows=historyData.events;
    $('#history-content').innerHTML=!rows.length
      ?empty('Chưa ghi nhận cảnh báo nào.')
      :`<table>
        <thead><tr><th>THỜI GIAN NHẬN</th><th>CẢNH BÁO</th><th>THIẾT BỊ</th><th>GỬI THÔNG BÁO</th></tr></thead>
        <tbody>${rows.map(e=>
          `<tr>
            <td>${stamp(e.received)}<small>${esc(e.id)}</small></td>
            <td>${badge(e.payload.kind==='FIRE'?'Phát hiện lửa':'Gas vượt ngưỡng','bad')}<small>ADC: ${esc(e.payload.gas_adc)} · gửi trễ ${Math.floor(e.payload.age_ms/1000)}s</small></td>
            <td>${esc(e.payload.device)}</td>
            <td>${e.deliveries.length
              ?e.deliveries.map(d=>badge(
                `${d.channel}: ${deliveryNames[d.status]||d.status}`,
                d.status==='failed'?'bad':d.status==='accepted'?'good':'neutral'
              )).join(' ')
              :'Không bật kênh gửi'}
            </td>
          </tr>`
        ).join('')}</tbody>
      </table>
      <p class="panel-note">“Dịch vụ đã nhận” chưa chứng minh SMS đã đến điện thoại. Kiểm tra trạng thái giao tin trong nhà cung cấp.</p>`;
  }else{
    const rows=historyData.activities;
    $('#history-content').innerHTML=!rows.length
      ?empty('Chưa nhận được trạng thái phần cứng.')
      :`<table>
        <thead><tr><th>THỜI GIAN NHẬN</th><th>THÀNH PHẦN</th><th>TRƯỚC</th><th>SAU</th></tr></thead>
        <tbody>${rows.map(r=>
          `<tr>
            <td>${stamp(r.received)}</td>
            <td>${esc(componentNames[r.component]||r.component)}</td>
            <td>${esc(componentValue(r.component,r.old_value))}</td>
            <td>${esc(componentValue(r.component,r.new_value))}</td>
          </tr>`
        ).join('')}</tbody>
      </table>
      <p class="panel-note">Ghi lại thay đổi quan sát qua MQTT. Những chuyển đổi xảy ra giữa hai mẫu đo hoặc khi mất mạng có thể không được ghi nhận.</p>`;
  }
}

function paintUsers(){
  const q=$('#user-search').value.toLowerCase();
  const rows=users.filter(u=>(u.username+' '+u.full_name).toLowerCase().includes(q));
  $('#user-count').textContent=`${users.length} tài khoản · ${users.filter(u=>u.active).length} đang hoạt động`;
  $('#users-content').innerHTML=!rows.length
    ?empty('Không có tài khoản phù hợp.')
    :`<table>
      <thead><tr><th>NGƯỜI DÙNG</th><th>VAI TRÒ</th><th>QUYỀN TRUY CẬP</th><th>TRẠNG THÁI</th><th>THAO TÁC</th></tr></thead>
      <tbody>${rows.map(u=>
        `<tr>
          <td><strong>${esc(u.full_name)}</strong><small>@${esc(u.username)}${u.id===user.id?' · Bạn':''}</small></td>
          <td>${badge(u.role==='admin'?'Admin':'Người dùng',u.role==='admin'?'good':'neutral')}</td>
          <td>${u.role==='admin'?'Toàn quyền':u.permissions.map(p=>badge(permissionNames[p])).join(' ')||'Chưa cấp quyền'}</td>
          <td>${badge(u.active?'Hoạt động':'Đã khóa',u.active?'good':'warn')}${u.must_change?'<small>Cần đổi mật khẩu</small>':''}</td>
          <td><div class="table-actions">
            <button class="secondary" data-edit="${u.id}">Sửa quyền</button>
            ${u.id!==user.id
              ?`<button class="secondary" data-reset="${u.id}">Mật khẩu</button><button class="secondary danger-button" data-delete="${u.id}">Xóa</button>`
              :''}
          </div></td>
        </tr>`
      ).join('')}</tbody>
    </table>`;
}

const auditActions={
  login:'Đăng nhập',
  create_user:'Tạo tài khoản',
  update_user:'Cập nhật quyền / trạng thái',
  delete_user:'Xóa tài khoản',
  reset_password:'Đặt lại mật khẩu',
  change_password:'Đổi mật khẩu',
  create_first_admin:'Tạo Admin ban đầu'
};

async function loadPage(){
  if(!user||user.must_change)return;
  if(page==='overview')paintOverview(await api('/api/device/status'));
  if(page==='thresholds')paintThresholds(await api('/api/device/thresholds'));
  if(page==='history'){historyData=await api('/api/history');paintHistory();}
  if(page==='users'){users=(await api('/api/admin/users')).users;paintUsers();}
  if(page==='audit'){
    const rows=(await api('/api/admin/audit')).rows;
    $('#audit-content').innerHTML=!rows.length
      ?empty('Chưa có nhật ký.')
      :`<table>
        <thead><tr><th>THỜI GIAN</th><th>NGƯỜI THỰC HIỆN</th><th>THAO TÁC</th><th>TÀI KHOẢN</th></tr></thead>
        <tbody>${rows.map(r=>
          `<tr>
            <td>${stamp(r.occurred)}</td>
            <td>${esc(r.actor)}</td>
            <td>${esc(auditActions[r.action]||r.action)}</td>
            <td>${esc(r.target)}</td>
          </tr>`
        ).join('')}</tbody>
      </table>`;
  }
}

function roleChanged(){
  const admin=$('#user-form').elements.role.value==='admin';
  $('#permissions-fieldset').disabled=admin;
}

function openUser(id){
  const form=$('#user-form');
  form.reset();
  const u=users.find(x=>x.id===id);
  form.elements.id.value=id||'';
  form.elements.username.disabled=!!u;
  $('#temporary-password-label').hidden=!!u;
  form.elements.password.required=!u;
  $('#user-dialog-title').textContent=u?'Chỉnh sửa tài khoản':'Thêm người dùng';
  $('#user-form-error').textContent='';

  if(u){
    for(const k of ['full_name','username','role'])form.elements[k].value=u[k];
    form.elements.active.value=String(u.active);
  }

  Object.keys(permissionNames).forEach(p=>form.elements[p].checked=u?u.permissions.includes(p):true);
  $('#user-form-note').textContent=u
    ?'Thay đổi quyền hoặc khóa tài khoản sẽ thu hồi các phiên đăng nhập của người dùng.'
    :'Người dùng mới phải đổi mật khẩu khi đăng nhập lần đầu.';
  roleChanged();
  $('#user-dialog').showModal();
}

$('#login-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const f=e.currentTarget;
  const button=f.querySelector('button');
  button.disabled=true;
  $('#login-error').textContent='';
  try{
    const s=await api('/api/login','POST',Object.fromEntries(new FormData(f)));
    user=s.user;
    csrf=s.csrf;
    f.reset();
    paintUser();
    await navigate(firstPage());
  }catch(err){
    $('#login-error').textContent=err.message;
  }finally{
    button.disabled=false;
  }
});

$('#logout').addEventListener('click',async()=>{
  try{
    await api('/api/logout','POST',{});
    showLogin();
    await refreshSession();
  }catch(e){
    toast(e.message,true);
  }
});

$('#nav').addEventListener('click',e=>{
  const b=e.target.closest('button[data-page]');
  if(b)navigate(b.dataset.page);
});

$('#password-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=e.currentTarget;
  const values=Object.fromEntries(new FormData(form));
  if(values.new!==values.repeat){
    toast('Mật khẩu mới nhập lại chưa khớp.',true);
    return;
  }

  const button=form.querySelector('button');
  button.disabled=true;
  try{
    await api('/api/password','POST',values);
    form.reset();
    await refreshSession();
    await navigate('account');
    toast('Đã đổi mật khẩu.');
  }catch(err){
    toast(err.message,true);
  }finally{
    button.disabled=false;
  }
});

$('#add-user').addEventListener('click',()=>openUser());
$('#user-search').addEventListener('input',paintUsers);
$('#user-form').elements.role.addEventListener('change',roleChanged);

$('#user-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=e.currentTarget;
  const id=form.elements.id.value;
  const data={
    full_name:form.elements.full_name.value,
    username:form.elements.username.value,
    password:form.elements.password.value,
    role:form.elements.role.value,
    active:form.elements.active.value==='true',
    permissions:Object.keys(permissionNames).filter(p=>form.elements[p].checked)
  };

  const submit=form.querySelector('[type=submit]');
  submit.disabled=true;
  try{
    await api(id?`/api/admin/users/${id}`:'/api/admin/users',id?'PATCH':'POST',data);
    $('#user-dialog').close();
    await loadPage();
    toast('Đã lưu tài khoản.');
  }catch(err){
    $('#user-form-error').textContent=err.message;
  }finally{
    submit.disabled=false;
  }
});

$('#users-content').addEventListener('click',async e=>{
  const b=e.target.closest('button');
  if(!b)return;

  if(b.dataset.edit){
    openUser(Number(b.dataset.edit));
    return;
  }

  if(b.dataset.reset){
    const u=users.find(u=>u.id===Number(b.dataset.reset));
    $('#reset-form').reset();
    $('#reset-form').elements.id.value=u.id;
    $('#reset-target').textContent=`Tài khoản: ${u.username}`;
    $('#reset-dialog').showModal();
    return;
  }

  if(b.dataset.delete){
    const u=users.find(u=>u.id===Number(b.dataset.delete));
    if(!confirm(`Xóa tài khoản ${u.username}? Người này sẽ mất quyền truy cập.`))return;
    try{
      await api(`/api/admin/users/${u.id}`,'DELETE');
      await loadPage();
      toast('Đã xóa tài khoản.');
    }catch(err){
      toast(err.message,true);
    }
  }
});

$('#reset-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const f=e.currentTarget;
  try{
    await api(`/api/admin/users/${f.elements.id.value}/reset-password`,'POST',{password:f.elements.password.value});
    $('#reset-dialog').close();
    f.reset();
    await loadPage();
    toast('Đã đặt lại mật khẩu.');
  }catch(err){
    toast(err.message,true);
  }
});

$$('.close-dialog').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$$('.tab').forEach(b=>b.addEventListener('click',()=>{
  historyTab=b.dataset.history;
  paintHistory();
}));

for(const id of ['#refresh-history','#refresh-audit']){
  $(id).addEventListener('click',()=>loadPage().catch(e=>toast(e.message,true)));
}

$('#today').textContent=new Date().toLocaleDateString('vi-VN',{
  weekday:'long',
  day:'2-digit',
  month:'long',
  year:'numeric'
});

async function tick(){
  if(busy||!user||document.hidden)return;
  busy=true;
  try{
    if(!await refreshSession())return;
    if(user.must_change||!allowed(page)){
      await navigate(user.must_change?'account':firstPage());
      return;
    }
    if(['overview','thresholds','history'].includes(page))await loadPage();
  }catch(e){
    if(page==='overview'){
      $('#connection-badge').textContent='● Mất kết nối máy chủ';
      $('#connection-badge').className='badge warn';
      $('#stale-warning').hidden=false;
      $('#stale-warning').textContent='Không cập nhật được dữ liệu. Các giá trị bên dưới là lần hiển thị cuối.';
    }else{
      toast(e.message,true);
    }
  }finally{
    busy=false;
  }
}

(async()=>{
  try{
    if(await refreshSession())await navigate(firstPage());
  }catch(e){
    $('#login-error').textContent=e.message;
  }
})();

setInterval(tick,2000);