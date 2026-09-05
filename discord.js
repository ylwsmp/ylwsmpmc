import {Router} from 'express';
const router=Router();
const orders=[];
router.post('/',(req,res)=>{orders.push({...req.body,date:new Date()});res.json({ok:true});});
router.get('/',(req,res)=>res.json(orders));
export default router;
